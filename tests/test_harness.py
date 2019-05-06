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

    def test_original_client_fails_and_corrected_client_passes(self):
        fixture = json.loads((ROOT / "examples/retry.json").read_text())
        command = [sys.executable, str(ROOT / "examples/inventory_client.py")]
        broken = check_client(fixture, command + ["--faulty"])
        fixed = check_client(fixture, command)
        self.assertFalse(broken["passed"])
        self.assertFalse(broken["checks"]["application_output"])
        self.assertEqual(broken["consumed"], 1)
        self.assertTrue(fixed["passed"])
        self.assertEqual(fixed["application"]["output"], {"available": 7})

    def test_application_output_is_checked_even_without_protocol_errors(self):
        fixture = {
            "application": {"expected_json": {"ok": True}},
            "interactions": [
                {
                    "request": {"method": "GET", "path": "/"},
                    "response": {"json": {"ok": True}},
                }
            ],
        }
        result = check_client(fixture, [sys.executable, "-c", "print('{}')"])
        self.assertFalse(result["passed"])
        self.assertEqual(result["unexpected"], 0)
        self.assertFalse(result["checks"]["application_output"])
