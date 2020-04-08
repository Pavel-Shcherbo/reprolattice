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

    def assertion_fixture(self):
        return {
            "application": {
                "assertions": [
                    {
                        "id": "dynamic-id",
                        "path": "/id",
                        "op": "type",
                        "value": "string",
                    },
                    {
                        "id": "accepted",
                        "path": "/accepted",
                        "op": "equals",
                        "value": True,
                    },
                    {
                        "id": "price",
                        "path": "/price",
                        "op": "approx",
                        "value": 100,
                        "atol": 0.01,
                    },
                ]
            },
            "interactions": [
                {
                    "request": {"method": "GET", "path": "/"},
                    "response": {"json": {"ok": True}},
                }
            ],
        }

    def output_command(self, output):
        source = (
            "import os, urllib.request; "
            'urllib.request.urlopen(os.environ["REPROLATTICE_BASE_URL"] + "/").read(); '
            f"print({json.dumps(output)!r})"
        )
        return [sys.executable, "-c", source]

    def test_assertions_accept_dynamic_output_and_redact_secrets(self):
        fixture = self.assertion_fixture()
        output = {
            "id": "generated-42",
            "accepted": True,
            "price": 100.005,
            "token": "private",
        }
        result = check_client(fixture, self.output_command(output))
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["assertions"]), 3)
        self.assertNotIn("private", json.dumps(result))

    def test_assertions_detect_boolean_number_and_missing_fields(self):
        for output in [
            {"id": "a", "accepted": 1, "price": 100},
            {"accepted": True, "price": 100},
            {"id": "a", "accepted": True, "price": 101},
        ]:
            with self.subTest(output=output):
                result = check_client(
                    self.assertion_fixture(), self.output_command(output)
                )
                self.assertFalse(result["passed"])
                self.assertTrue(result["checks"]["all_interactions_consumed"])
                self.assertFalse(result["checks"]["application_assertions"])

    def test_legacy_expected_json_also_uses_typed_equality(self):
        fixture = self.assertion_fixture()
        fixture["application"] = {"expected_json": {"accepted": True}}
        result = check_client(fixture, self.output_command({"accepted": 1}))
        self.assertFalse(result["checks"]["application_output"])

    def test_invalid_rules_fail_before_starting_application(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "started"
            fixture = self.assertion_fixture()
            fixture["application"]["assertions"][0]["op"] = "typo"
            with self.assertRaises(ValueError):
                check_client(
                    fixture,
                    [sys.executable, "-c", f'open({str(marker)!r}, "w").close()'],
                )
            self.assertFalse(marker.exists())

    def test_output_limit_fails_even_when_an_exit_code_is_expected(self):
        fixture = self.assertion_fixture()
        result = check_client(
            fixture,
            [sys.executable, "-c", 'import os;\nwhile True: os.write(2, b"x" * 65536)'],
        )
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["within_output_limit"])
        self.assertLessEqual(len(result["application"]["stderr"]), 8192)
