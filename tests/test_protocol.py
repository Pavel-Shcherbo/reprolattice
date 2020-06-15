import unittest

from reprolattice.protocol import verify_protocol


class ProtocolTests(unittest.TestCase):
    def fixture(self):
        return {
            "interactions": [
                {
                    "request": {
                        "method": "POST",
                        "path_pattern": "/orders/*",
                        "headers": {"X-Tenant": "demo"},
                        "query_assertions": [
                            {"path": "/limit", "op": "equals", "value": "10"}
                        ],
                        "json_assertions": [
                            {"path": "/quantity", "op": "gte", "value": 1}
                        ],
                    },
                    "sample_request": {
                        "method": "POST",
                        "path": "/orders/42?limit=10",
                        "headers": {"X-Tenant": "demo"},
                        "json": {"quantity": 3},
                    },
                    "response": {"json": {"accepted": True}},
                }
            ]
        }

    def test_dynamic_example_runs_over_real_http(self):
        result = verify_protocol(self.fixture())
        self.assertTrue(result["passed"])
        self.assertEqual(result["consumed"], 1)
        self.assertEqual(result["results"][0]["body"], {"accepted": True})

    def test_missing_or_invalid_sample_fails_before_serving(self):
        fixture = self.fixture()
        fixture["interactions"][0].pop("sample_request")
        with self.assertRaisesRegex(ValueError, "sample_request"):
            verify_protocol(fixture)
        fixture = self.fixture()
        fixture["interactions"][0]["sample_request"]["json"]["quantity"] = 0
        with self.assertRaisesRegex(ValueError, "does not satisfy"):
            verify_protocol(fixture)

    def test_exact_headers_and_bodyless_responses(self):
        for method, status in [("HEAD", 200), ("GET", 204), ("GET", 304)]:
            with self.subTest(method=method, status=status):
                result = verify_protocol(
                    {
                        "interactions": [
                            {
                                "request": {
                                    "method": method,
                                    "path": "/",
                                    "headers": {"X-Test": "yes"},
                                },
                                "response": {"status": status},
                            }
                        ]
                    }
                )
                self.assertTrue(result["passed"])

