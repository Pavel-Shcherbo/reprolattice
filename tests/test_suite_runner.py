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

