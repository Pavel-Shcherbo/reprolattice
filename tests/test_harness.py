import json
import sys
import unittest
from pathlib import Path

from reprolattice.harness import check_client

ROOT = Path(__file__).resolve().parents[1]


class HarnessTests(unittest.TestCase):
    def test_slow_client_is_stopped_and_reported(self):
        fixture = json.loads((ROOT / "examples/retry.json").read_text())
        report = check_client(
            fixture, [sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.1
        )
        self.assertFalse(report["passed"])
        self.assertFalse(report["checks"]["within_time_limit"])
        self.assertIsNotNone(report["application"]["returncode"])

