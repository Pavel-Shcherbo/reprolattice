"""Saved suite evidence, strict browser requests and coherent baseline review."""

import copy
import json
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from reprolattice.archive_web import PROJECT
from reprolattice.run_contract import canonical, fingerprint
from reprolattice.run_registry import RunRegistry
from reprolattice.suite_web import evaluate_suite
from reprolattice.web import evaluate
from test_run_registry import report


class ArchiveWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.healthy = evaluate_suite({"mode": "suite", "jobs": 2})["report"]
        cls.faulty = evaluate_suite(
            {"mode": "suite", "jobs": 2, "faulty_client": True}
        )["report"]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "state"
        self.environment = patch.dict(
            "os.environ", {"REPROLATTICE_STATE_DIR": str(self.root)}
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def api(self, action, **fields):
        return evaluate({"mode": "archive", "action": action, **fields})

    def save(self, value=None, key="first", label="Reviewed control"):
        return self.api(
            "archive",
            report=copy.deepcopy(value or self.healthy),
            request_key=key,
            label=label,
        )["record"]

    def registry(self):
        return RunRegistry(self.root / "run-workbench/runs.sqlite")

    def test_empty_overview_and_invalid_requests_do_not_initialize_database(self):
        self.assertFalse(self.api("overview")["initialized"])
        self.assertFalse((self.root / "run-workbench/runs.sqlite").exists())
        bad = [
            {"action": "archive", "report": {}, "request_key": "bad"},
            {"action": "inspect", "record": "../../outside"},
            {"action": "overview", "after": True},
            {"action": "overview", "after": 2**64},
            {"action": "overview", "project": "other"},
            {"action": "history", "source": "case", "status": []},
            {
                "action": "move",
                "name": "accepted",
                "record": "a" * 64,
                "generation": 0,
                "reason": " ",
            },
            {
                "action": "compare",
                "record": "a" * 64,
                "before": "b" * 64,
                "baseline": "accepted",
            },
            {
                "action": "archive",
                "report": self.healthy,
                "request_key": "good",
                "command": ["bad"],
            },
        ]
        for request in bad:
            with (
                self.subTest(request=request.get("action")),
                self.assertRaises(ValueError),
            ):
                evaluate({"mode": "archive", **request})
        self.assertFalse((self.root / "run-workbench/runs.sqlite").exists())

    def test_real_suite_save_retry_and_reopen_preserve_exact_report(self):
        first = self.save()
        repeated = self.save()
        self.assertEqual(first["id"], repeated["id"])
        self.assertTrue(repeated["reused"])
        self.assertEqual(
            self.api("inspect", record=first["id"])["record"]["report"], self.healthy
        )
        self.assertEqual(
            self.registry().get(PROJECT, first["id"])["context"],
            self.healthy["execution_context"],
        )
        with self.assertRaisesRegex(ValueError, "conflicts"):
            self.save(label="Changed label")
        self.assertEqual(len(self.api("overview")["items"]), 1)
        self.assertEqual(len(first["revision"]), 64)

    def test_actual_faulty_run_explains_three_regressions_and_reverse_fixes(self):
        before = self.save()
        after = self.save(self.faulty, key="faulty", label="Faulty client")
        changed = self.api("compare", before=before["id"], record=after["id"])
        self.assertEqual(changed["counts"], {"regressed": 3, "stable_pass": 2})
        self.assertFalse(changed["gate"]["passed"])
        self.assertEqual(changed["changed_input_cases"], 0)
        self.assertEqual(sum(item["subject_changed"] for item in changed["changes"]), 4)
        fixed = self.api("compare", before=after["id"], record=before["id"])
        self.assertEqual(fixed["counts"], {"fixed": 3, "stable_pass": 2})
        self.assertTrue(fixed["gate"]["passed"])

    def test_green_baseline_reason_events_and_stale_generation_fencing(self):
        green = self.save()
        bad = self.save(self.faulty, key="bad")
        self.assertIsNone(self.api("baseline", name="accepted")["baseline"])
        with self.assertRaisesRegex(ValueError, "fully executed passing"):
            self.api(
                "move",
                name="accepted",
                record=bad["id"],
                generation=0,
                reason="Invalid candidate",
            )
        moved = self.api(
            "move",
            name="accepted",
            record=green["id"],
            generation=0,
            reason="Five isolated checks passed",
        )
        self.assertEqual(moved["generation"], 1)
        state = self.api("baseline", name="accepted")
        self.assertEqual(state["events"][0]["reason"], "Five isolated checks passed")
        self.assertEqual(state["baseline"]["record_id"], green["id"])
        comparison = self.api(
            "compare", baseline="accepted", generation=1, record=bad["id"]
        )
        self.assertEqual(comparison["baseline"]["generation"], 1)
        self.assertEqual(comparison["before_record"], green["id"])
        with self.assertRaisesRegex(ValueError, "generation conflict"):
            self.api(
                "move",
                name="accepted",
                record=green["id"],
                generation=0,
                reason="Stale page",
            )
        self.api(
            "move",
            name="accepted",
            record=green["id"],
            generation=1,
            reason="Rechecked same content",
        )
        with self.assertRaisesRegex(ValueError, "generation conflict"):
            self.api("compare", baseline="accepted", generation=1, record=bad["id"])
        self.assertEqual(
            self.api("baseline", name="accepted")["baseline"]["generation"], 2
        )

    def test_filtered_suite_cannot_be_promoted_even_when_selected_case_passed(self):
        partial = self.save(report(("passed", "skipped"), full=False))
        with self.assertRaisesRegex(ValueError, "fully executed passing"):
            self.api(
                "move",
                name="accepted",
                record=partial["id"],
                generation=0,
                reason="Only selected case passed",
            )
        self.assertIsNone(self.api("baseline", name="accepted")["baseline"])

    def test_case_history_contains_all_variants_and_status_filter_is_exact(self):
        self.save()
        self.save(self.faulty, key="faulty")
        history = self.api("history", source="retry-quantity")
        self.assertEqual(len(history["items"]), 6)
        failures = self.api("history", source="retry-quantity", status="failed")
        self.assertEqual(len(failures["items"]), 3)
        self.assertTrue(all(item["status"] == "failed" for item in failures["items"]))
        self.assertIsNone(history["next_cursor"])

    def test_saved_junit_matches_immutable_report_counts(self):
        saved = self.save(self.faulty)
        exported = self.api("junit", record=saved["id"])
        self.assertEqual(exported["record"], saved["id"])
        document = ET.fromstring(exported["junit_xml"]).find("testsuite")
        self.assertEqual(document.get("tests"), "5")
        self.assertEqual(document.get("failures"), "3")
        self.assertEqual(len(document.findall("testcase")), 5)

    def test_listing_is_metadata_but_inspection_and_baseline_verify_payload(self):
        saved = self.save()
        self.api(
            "move", name="accepted", record=saved["id"], generation=0, reason="Reviewed"
        )
        registry = self.registry()
        with registry._tx() as db:
            db.execute("UPDATE runs SET report=? WHERE id=?", (b"{}", saved["id"]))
        self.assertEqual(self.api("overview")["items"][0]["id"], saved["id"])
        with self.assertRaises(ValueError):
            self.api("inspect", record=saved["id"])
        with self.assertRaises(ValueError):
            self.api("baseline", name="accepted")

    def test_manually_damaged_baseline_pointer_cannot_qualify_a_failed_target(self):
        green = self.save()
        failed = self.save(self.faulty, key="failed")
        self.api(
            "move",
            name="accepted",
            record=green["id"],
            generation=0,
            reason="Reviewed green run",
        )
        with self.registry()._tx() as db:
            db.execute(
                "UPDATE baselines SET record_id=? WHERE project=? AND name=?",
                (failed["id"], PROJECT, "accepted"),
            )
        with self.assertRaisesRegex(ValueError, "not a complete passing suite"):
            self.api("baseline", name="accepted")
        with self.assertRaisesRegex(ValueError, "not a complete passing suite"):
            self.api("compare", baseline="accepted", generation=1, record=green["id"])

    def test_foreign_project_records_are_not_exposed_by_workbench(self):
        saved = self.save()
        registry = self.registry()
        registry.project("other")
        foreign = registry.record(
            "other", self.faulty, revision="a" * 40, request_key="foreign"
        )
        with self.assertRaisesRegex(ValueError, "unknown archived run"):
            self.api("inspect", record=foreign["id"])
        self.assertEqual(
            [item["id"] for item in self.api("overview")["items"]], [saved["id"]]
        )

    def test_concurrent_first_archives_are_idempotent_in_one_project(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            values = list(pool.map(lambda _: self.save(), range(4)))
        self.assertEqual(len({item["id"] for item in values}), 1)
        self.assertEqual(len(self.api("overview")["items"]), 1)


class RegistryReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.registry = RunRegistry(Path(self.temp.name) / "runs.sqlite", create=True)
        self.registry.project("review")
        self.saved = []
        for index in range(3):
            self.saved.append(
                self.registry.record(
                    "review",
                    report(),
                    revision="a" * 40,
                    request_key="run-" + str(index),
                )
            )

    def test_newest_first_cursor_is_stable_while_new_runs_arrive(self):
        page = self.registry.list("review", limit=1, order="newest")
        self.assertEqual(page["items"][0]["id"], self.saved[2]["id"])
        self.registry.record("review", report(), revision="b" * 40, request_key="later")
        older = self.registry.list(
            "review", after=page["next_cursor"], limit=2, order="newest"
        )
        self.assertEqual(
            [item["id"] for item in older["items"]],
            [self.saved[1]["id"], self.saved[0]["id"]],
        )
        self.assertIsNone(older["next_cursor"])
        with self.assertRaises(ValueError):
            self.registry.list("review", order="random")

    def test_baseline_listing_and_coherent_history_have_continuation_cursors(self):
        for index in range(27):
            self.registry.move_baseline(
                "review",
                f"baseline-{index:02d}",
                self.saved[0]["id"],
                expected_generation=0,
                reason="Reviewed",
            )
        first = self.registry.baselines("review", limit=25)
        second = self.registry.baselines("review", after=first["next_cursor"], limit=25)
        self.assertEqual(len(first["items"]), 25)
        self.assertEqual(len(second["items"]), 2)
        self.assertFalse(
            {item["name"] for item in first["items"]}
            & {item["name"] for item in second["items"]}
        )
        for generation in range(1, 4):
            self.registry.move_baseline(
                "review",
                "baseline-00",
                self.saved[generation % 3]["id"],
                expected_generation=generation,
                reason="Rechecked",
            )
        view = self.registry.baseline_view("review", "baseline-00", limit=2)
        self.assertEqual(view["baseline"]["generation"], 4)
        self.assertEqual(len(view["events"]), 2)
        more = self.registry.baseline_view(
            "review", "baseline-00", after=view["next_cursor"], limit=2
        )
        self.assertEqual([item["generation"] for item in more["events"]], [3, 4])
        self.assertIsNone(more["next_cursor"])

    def test_baseline_comparison_binds_record_and_generation_in_one_read_view(self):
        self.registry.move_baseline(
            "review",
            "accepted",
            self.saved[0]["id"],
            expected_generation=0,
            reason="Initial",
        )
        compared = self.registry.compare_baseline(
            "review", "accepted", self.saved[1]["id"], expected_generation=1
        )
        self.assertEqual(compared["before_record"], self.saved[0]["id"])
        self.assertTrue(compared["gate"]["passed"])
        self.assertEqual(
            fingerprint(
                {key: value for key, value in compared.items() if key != "sha256"}
            ),
            compared["sha256"],
        )
        self.registry.move_baseline(
            "review",
            "accepted",
            self.saved[2]["id"],
            expected_generation=1,
            reason="New result",
        )
        with self.assertRaisesRegex(ValueError, "generation conflict"):
            self.registry.compare_baseline(
                "review", "accepted", self.saved[1]["id"], expected_generation=1
            )
        self.assertEqual(
            self.registry.compare_baseline(
                "review", "accepted", self.saved[1]["id"], expected_generation=2
            )["before_record"],
            self.saved[2]["id"],
        )

    def test_unknown_project_and_invalid_baseline_parameters_cannot_read_or_mutate(
        self,
    ):
        for operation in (
            lambda: self.registry.baselines("other"),
            lambda: self.registry.baseline_view("other", "accepted"),
            lambda: self.registry.baseline_view("review", "accepted", after=True),
            lambda: self.registry.baseline_view("review", "accepted", after=2**64),
            lambda: self.registry.baselines("review", after="../outside"),
            lambda: self.registry.compare_baseline(
                "review", "accepted", self.saved[0]["id"], expected_generation=True
            ),
        ):
            with self.assertRaises(ValueError):
                operation()
