"""Archive immutability, baseline fencing and independently classified regressions."""

import copy
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

from reprolattice.run_contract import fingerprint, validate_run
from reprolattice.run_compare import comparison
from reprolattice.run_registry import RunRegistry
from reprolattice.suite_config import compile_suite
from reprolattice.suite_runner import run_suite

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
CONTEXT = {"runner": "controlled-test"}


def report(statuses=("passed",), *, names=None, full=True):
    cases = []
    for index, status in enumerate(statuses):
        name = names[index] if names else "case-" + str(index + 1)
        case = {
            "id": name,
            "source_id": name,
            "mode": "application",
            "tags": ["unit"],
            "parameters": {},
            "parameters_sha256": fingerprint({}),
            "artifact_contract_sha256": fingerprint([]),
            "timeout_seconds": 10,
            "fixture_sha256": "a" * 64,
            "command_sha256": "b" * 64,
            "inputs": [],
            "sqlite_definitions": [],
            "status": status,
            "duration_seconds": 1.0,
        }
        if status in ("passed", "failed", "error"):
            case["detail"] = {
                "passed": status == "passed",
                "checks": {"value": status == "passed"},
            }
        if status == "error":
            case["error"] = {"type": "RuntimeError", "message": "controlled error"}
        if status == "skipped":
            case["reason"] = "tag_filter" if not full else "fail_fast"
        cases.append(case)
    counts = {
        status: sum(c["status"] == status for c in cases)
        for status in ("passed", "failed", "error", "skipped", "cancelled")
    }
    selected = len(cases) - sum(c.get("reason") == "tag_filter" for c in cases)
    passed = counts["passed"] == selected and not any(
        counts[key] for key in ("failed", "error", "cancelled")
    )
    return {
        "format": "reprolattice.suite-report.v1",
        "suite": "controlled",
        "run_id": str(uuid.uuid4()),
        "suite_sha256": "c" * 64,
        "definition_sha256": "d" * 64,
        "started_at": "2026-11-04T10:00:00Z",
        "finished_at": "2026-11-04T10:00:02Z",
        "duration_seconds": 2.0,
        "execution_context": CONTEXT,
        "selected_cases": selected,
        "total_cases": len(cases),
        "full_suite": selected == len(cases),
        "passed": passed,
        "counts": counts,
        "cases": cases,
    }


def compare(a, b, policy=None):
    return comparison(
        a, b, before_context=CONTEXT, after_context=CONTEXT, policy=policy
    )


class RunComparisonTests(unittest.TestCase):
    def test_regression_fix_existing_failure_and_subject_change_are_distinct(self):
        before = report(("passed", "failed", "failed"))
        after = report(("failed", "passed", "failed"))
        after["cases"][0]["command_sha256"] = "e" * 64
        result = compare(before, after)
        self.assertEqual(
            result["counts"], {"fixed": 1, "regressed": 1, "stable_failure": 1}
        )
        self.assertEqual(result["subject_changed_cases"], 1)
        self.assertFalse(result["gate"]["passed"])
        self.assertEqual(
            {item["code"] for item in result["gate"]["findings"]},
            {"regression", "candidate_failure"},
        )
        self.assertTrue(
            compare(
                report(("failed",)),
                report(("failed",)),
                {"allow_existing_failures": True},
            )["gate"]["passed"]
        )

    def test_fixture_changes_do_not_masquerade_as_fixes(self):
        a = report(("failed",))
        b = report()
        b["cases"][0]["fixture_sha256"] = "f" * 64
        result = compare(a, b)
        self.assertEqual(result["counts"], {"changed_inputs": 1})
        self.assertFalse(result["gate"]["passed"])
        self.assertTrue(compare(a, b, {"allow_changed_inputs": True})["gate"]["passed"])

    def test_subject_file_role_allows_code_changes_without_changing_oracle(self):
        a = report()
        b = report(("failed",))
        for value, digest in [(a, "1" * 64), (b, "2" * 64)]:
            value["cases"][0]["inputs"] = [
                {"path": "client.py", "role": "subject", "sha256": digest, "bytes": 10}
            ]
        self.assertEqual(compare(a, b)["counts"], {"regressed": 1})
        a["cases"][0]["inputs"][0]["role"] = "fixture"
        b["cases"][0]["inputs"][0]["role"] = "fixture"
        self.assertEqual(compare(a, b)["counts"], {"changed_inputs": 1})

    def test_reordered_matrix_variants_pair_by_parameters_not_case_index(self):
        a = report(("passed", "passed"))
        b = report(("failed", "passed"))
        for value in (a, b):
            for index, case in enumerate(value["cases"]):
                case["source_id"] = "matrix"
                case["parameters"] = {"size": index + 1}
                case["parameters_sha256"] = fingerprint(case["parameters"])
        b["cases"].reverse()
        for index, case in enumerate(b["cases"]):
            case["id"] = "reordered-" + str(index)
        result = compare(a, b)
        self.assertEqual(result["counts"], {"regressed": 1, "stable_pass": 1})
        self.assertEqual(len(result["changes"]), 2)

    def test_removed_added_and_unexecuted_cases_block_greenwashing(self):
        a = report(("passed", "passed"), names=["a", "b"])
        b = report(("passed", "cancelled"), names=["a", "new"])
        result = compare(a, b)
        self.assertEqual(
            result["counts"], {"added_unexecuted": 1, "removed": 1, "stable_pass": 1}
        )
        self.assertFalse(result["gate"]["passed"])
        self.assertEqual(
            compare(report(), report(("skipped",)))["counts"], {"lost_coverage": 1}
        )

    def test_partial_selection_requires_explicit_scope_policy(self):
        a = report(("passed", "passed"))
        b = report(("passed", "skipped"), full=False)
        self.assertFalse(compare(a, b)["gate"]["passed"])
        scoped = compare(
            a, b, {"require_full_suite": False, "allow_tag_filtered": True}
        )
        self.assertTrue(scoped["gate"]["passed"])
        self.assertFalse(scoped["after_full_suite"])

    def test_context_unknown_legacy_and_single_run_timing_are_explicit(self):
        a = report()
        b = report()
        b["cases"][0]["duration_seconds"] = 3
        self.assertFalse(compare(a, b, {"max_slowdown_ratio": 2})["gate"]["passed"])
        self.assertTrue(compare(a, b)["gate"]["passed"])
        self.assertFalse(comparison(a, b)["gate"]["passed"])
        self.assertFalse(
            comparison(
                a, b, before_context={"python": "old"}, after_context={"python": "new"}
            )["gate"]["passed"]
        )
        for value in (a, b):
            for key in (
                "parameters_sha256",
                "artifact_contract_sha256",
                "timeout_seconds",
            ):
                value["cases"][0].pop(key)
        self.assertEqual(compare(a, b)["pairing_policy"], "legacy_case_id")
        self.assertFalse(compare(a, b)["gate"]["passed"])
        self.assertTrue(
            compare(a, b, {"allow_legacy_metadata": True})["gate"]["passed"]
        )

    def test_passed_case_contradiction_and_duplicate_pair_identity_rejected(self):
        value = report()
        value["cases"][0]["detail"]["checks"]["value"] = False
        with self.assertRaisesRegex(ValueError, "contradicts"):
            validate_run(value)
        value = report(("passed", "passed"))
        value["cases"][1]["source_id"] = value["cases"][0]["source_id"]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_run(value)

    def test_malformed_import_diagnostics_are_value_errors(self):
        invalid_context = report()
        invalid_context["execution_context"] = None
        with self.assertRaises(ValueError):
            validate_run(invalid_context)
        for field, value in [
            ("artifacts", [1]),
            ("sqlite", [{}]),
            ("detail", {"checks": []}),
            ("error", "invalid"),
        ]:
            invalid = report()
            invalid["cases"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_run(invalid)

    def test_extreme_finite_timings_keep_comparison_json_finite(self):
        before = report()
        after = report()
        before["cases"][0]["duration_seconds"] = 1e-320
        result = compare(before, after)
        json.dumps(result, allow_nan=False)
        self.assertTrue(result["changes"][0]["duration_ratio_overflow"])
        self.assertIsNone(result["changes"][0]["duration_ratio"])
        gated = compare(
            before, after, {"max_slowdown_ratio": 2, "minimum_duration_seconds": 1e-321}
        )
        self.assertFalse(gated["gate"]["passed"])


class RunRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.registry = RunRegistry(self.root / "runs.sqlite", create=True)
        self.registry.project("demo")

    def record(self, value=None, key="first", revision="1" * 40):
        return self.registry.record(
            "demo", value or report(), revision=revision, request_key=key
        )

