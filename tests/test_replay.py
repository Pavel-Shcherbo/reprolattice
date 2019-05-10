import http.client
import json
import threading
import unittest

from reprolattice.replay import make_server, redact, validate


class ReplayTests(unittest.TestCase):
    def test_order_mismatch_and_no_upstream_fallback(self):
        fixture = {
            "interactions": [
                {
                    "request": {"method": "POST", "path": "/event", "json": {"id": 1}},
                    "response": {"status": 503, "json": {"retry": True}},
                },
                {
                    "request": {"method": "POST", "path": "/event", "json": {"id": 1}},
                    "response": {"status": 200, "json": {"ok": True}},
                },
            ]
        }
        server, state = make_server(fixture)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def request(path, body):
            connection = http.client.HTTPConnection(
                "127.0.0.1", server.server_port, timeout=3
            )
            connection.request("POST", path, json.dumps(body))
            response = connection.getresponse()
            status = response.status
            response.read()
            connection.close()
            return status

        try:
            self.assertEqual(request("/unexpected", {}), 409)
            self.assertEqual(state["consumed"], 0)
            self.assertEqual(request("/event", {"id": 2}), 409)
            self.assertEqual(request("/event", {"id": 1}), 503)
            self.assertEqual(request("/event", {"id": 1}), 200)
            self.assertEqual(request("/event", {"id": 1}), 409)
            self.assertEqual(state, {"consumed": 2, "unexpected": 3, "total": 2})
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_redaction_is_recursive_and_does_not_mutate_input(self):
        source = {
            "headers": {"Authorization": "Bearer private", "X-API-Key": "key"},
            "events": [{"password": "private", "value": 3}],
        }
        cleaned = redact(source)
        self.assertNotIn("private", json.dumps(cleaned))
        self.assertEqual(cleaned["headers"]["X-API-Key"], "[REDACTED]")
        self.assertEqual(source["events"][0]["password"], "private")

    def test_reject_header_injection(self):
        with self.assertRaises(ValueError):
            validate(
                {
                    "interactions": [
                        {
                            "request": {"method": "GET", "path": "/"},
                            "response": {"headers": {"X-Test": "a\r\nb"}},
                        }
                    ]
                }
            )

