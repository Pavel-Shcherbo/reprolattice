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

