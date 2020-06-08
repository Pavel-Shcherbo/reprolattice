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

