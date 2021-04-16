import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from reprolattice.suite_config import compile_suite
from reprolattice.suite_runner import run_suite
from suite_fixtures import case, client_source, suite


class SuiteRunnerTests(unittest.TestCase):
    def run_cases(self, cases, **options):
        return run_suite(compile_suite(suite(cases)), **options)

    def test_pass_failure_and_launch_error_remain_distinct(self):
        report = self.run_cases(
            [
                case("pass"),
                case("fail", expected=False),
                case("error", command=["/not-an-installed-program"]),
            ]
        )
        self.assertEqual(
            [item["status"] for item in report["cases"]], ["passed", "failed", "error"]
        )
        self.assertEqual(
            report["counts"],
            {"passed": 1, "failed": 1, "error": 1, "skipped": 0, "cancelled": 0},
        )
        self.assertFalse(report["passed"])

    def test_fail_fast_preserves_not_started_case_without_side_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "started"
            report = self.run_cases(
                [
                    case("fail", expected=False),
                    case(
                        "pending",
                        command=[
                            sys.executable,
                            "-c",
                            f'open({str(marker)!r},"w").close()',
                        ],
                    ),
                ],
                fail_fast=True,
            )
            self.assertEqual(
                [item["status"] for item in report["cases"]], ["failed", "skipped"]
            )
            self.assertEqual(report["cases"][1]["reason"], "fail_fast")
            self.assertFalse(marker.exists())

    def test_fail_fast_cancels_an_inflight_case(self):
        slow = case(
            "slow", command=[sys.executable, "-c", "import time; time.sleep(30)"]
        )
        report = self.run_cases(
            [case("fail", expected=False), slow, case("pending")],
            jobs=2,
            fail_fast=True,
        )
        self.assertEqual(
            [item["status"] for item in report["cases"]],
            ["failed", "cancelled", "skipped"],
        )
        self.assertFalse(report["cases"][1]["detail"]["checks"]["not_cancelled"])

    def test_user_cancellation_accounts_for_every_selected_case(self):
        cancellation = threading.Event()
        timer = threading.Timer(0.15, cancellation.set)
        timer.start()
        try:
            report = self.run_cases(
                [
                    case(
                        "slow",
                        command=[sys.executable, "-c", "import time; time.sleep(30)"],
                    ),
                    case("pending"),
                ],
                should_cancel=cancellation.is_set,
            )
        finally:
            timer.cancel()
        self.assertEqual(
            [item["status"] for item in report["cases"]], ["cancelled", "cancelled"]
        )
        self.assertEqual(report["stop_reason"], "user_cancelled")
        self.assertFalse(report["passed"])

    def test_parallel_cases_overlap_but_results_keep_source_order(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "ready"
            wait_source = (
                "import time; from pathlib import Path; "
                f"p=Path({str(marker)!r}); deadline=time.monotonic()+2; "
                "\nwhile not p.exists() and time.monotonic()<deadline: time.sleep(0.01)\n"
                "assert p.exists();\n" + client_source()
            )
            signal_source = (
                f'from pathlib import Path; Path({str(marker)!r}).write_text("ready"); '
                + client_source()
            )
            report = self.run_cases(
                [
                    case("waiter", command=[sys.executable, "-c", wait_source]),
                    case("signaler", command=[sys.executable, "-c", signal_source]),
                ],
                jobs=2,
            )
            self.assertTrue(report["passed"], report)
            self.assertEqual(
                [item["id"] for item in report["cases"]], ["waiter", "signaler"]
            )
            self.assertEqual(
                [event["sequence"] for event in report["events"]], list(range(1, 5))
            )

    def test_workspace_isolation_and_output_artifact_assertions(self):
        source = client_source(
            extra='from pathlib import Path; assert not Path("counter.json").exists(); Path("counter.json").write_text("{\\"count\\":1}"); '
        )
        definitions = [
            case("first", command=[sys.executable, "-c", source]),
            case("second", command=[sys.executable, "-c", source]),
        ]
        for definition in definitions:
            definition["artifacts"] = [
                {
                    "path": "counter.json",
                    "kind": "json",
                    "assertions": [{"path": "/count", "op": "equals", "value": 1}],
                }
            ]
        report = self.run_cases(definitions, jobs=2)
        self.assertTrue(report["passed"], report)
        self.assertTrue(all(item["artifacts"][0]["passed"] for item in report["cases"]))
        definitions[1]["artifacts"][0]["assertions"][0]["value"] = True
        failed = self.run_cases(definitions)
        self.assertEqual(failed["cases"][1]["status"], "failed")
        self.assertTrue(failed["cases"][1]["detail"]["passed"])

    def test_tag_filter_records_partial_scope_and_rejects_empty_selection(self):
        first, second = case("core"), case("other")
        second["tags"] = ["extended"]
        plan = compile_suite(suite([first, second]))
        report = run_suite(plan, include_tags=["core"])
        self.assertTrue(report["passed"])
        self.assertFalse(report["full_suite"])
        self.assertEqual(report["selected_cases"], 1)
        self.assertEqual(report["cases"][1]["reason"], "tag_filter")
        with self.assertRaisesRegex(ValueError, "every case"):
            run_suite(plan, include_tags=["missing"])

    def test_explicit_secret_is_absent_from_retained_case_diagnostics(self):
        secret = "suite-secret-canary-5571"
        source = client_source(extra="import sys; print(sys.argv[1],file=sys.stderr); ")
        definition = case(
            "private", command=[sys.executable, "-c", source, "${credential}"]
        )
        definition.update(
            matrix={"credential": [secret]}, secret_parameters=["credential"]
        )
        report = self.run_cases([definition])
        self.assertTrue(report["passed"])
        self.assertNotIn(secret, json.dumps(report))
        self.assertIn(
            "[REDACTED]", report["cases"][0]["detail"]["application"]["stderr"]
        )

