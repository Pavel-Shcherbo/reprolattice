import http.client
import json
import tempfile
import threading
import subprocess
import sys
import selectors
import signal
import unittest
from pathlib import Path

from reprolattice.capture import (
    CapturePolicy,
    CaptureSession,
    make_capture_server,
    scrub_url,
    strict_json,
)
from reprolattice.replay import make_server, validate


class CaptureTests(unittest.TestCase):
    def start(self, fixture, policy=None):
        upstream, _ = make_server(fixture)
        proxy, session = make_capture_server(
            f"http://127.0.0.1:{upstream.server_port}", policy
        )
        servers = [upstream, proxy]
        threads = []
        for server in servers:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            threads.append(thread)

        def cleanup():
            for server in reversed(servers):
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join()

        self.addCleanup(cleanup)
        return proxy, session

    def request(self, port, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        try:
            connection.request(
                method,
                path,
                json.dumps(body) if body is not None else None,
                headers or {},
            )
            response = connection.getresponse()
            raw = response.read()
            return (
                response.status,
                json.loads(raw) if raw else None,
                dict(response.getheaders()),
            )
        finally:
            connection.close()

    def test_recorded_json_can_be_replayed_without_an_upstream(self):
        fixture = {
            "interactions": [
                {
                    "request": {"method": "GET", "path": "/items?q=a%20b"},
                    "response": {"status": 200, "json": {"items": [1, 2]}},
                }
            ]
        }
        proxy, session = self.start(fixture)
        status, body, _ = self.request(proxy.server_port, "GET", "/items?q=a%20b")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"items": [1, 2]})
        captured = session.snapshot()
        self.assertTrue(captured["capture"]["complete"])
        self.assertEqual(
            captured["interactions"][0]["request"]["path"], "/items?q=a%20b"
        )
        replay, state = make_server(captured)
        thread = threading.Thread(target=replay.serve_forever, daemon=True)
        thread.start()
        try:
            replayed = self.request(replay.server_port, "GET", "/items?q=a%20b")
            self.assertEqual(replayed[:2], (200, {"items": [1, 2]}))
            self.assertEqual(state["consumed"], 1)
        finally:
            replay.shutdown()
            replay.server_close()
            thread.join()

    def test_secrets_are_forwarded_only_when_explicit_and_not_stored(self):
        fixture = {
            "interactions": [
                {
                    "request": {
                        "method": "POST",
                        "path": "/session?token=query-canary",
                        "json": {"password": "body-canary", "value": 4},
                    },
                    "response": {
                        "status": 200,
                        "json": {"access_token": "response-canary", "value": 4},
                        "headers": {"Set-Cookie": "cookie-canary"},
                    },
                }
            ]
        }
        proxy, session = self.start(
            fixture, CapturePolicy(allow_writes=True, allow_credentials=True)
        )
        status, body, headers = self.request(
            proxy.server_port,
            "POST",
            "/session?token=query-canary",
            {"password": "body-canary", "value": 4},
            {"Authorization": "Bearer header-canary"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["access_token"], "response-canary")
        self.assertEqual(headers["Set-Cookie"], "cookie-canary")
        captured = session.snapshot()
        serialized = json.dumps(captured)
        for canary in [
            "query-canary",
            "body-canary",
            "response-canary",
            "cookie-canary",
            "header-canary",
        ]:
            self.assertNotIn(canary, serialized)
        self.assertTrue(captured["capture"]["complete"])
        self.assertTrue(captured["capture"]["requires_review"])
        self.assertTrue(captured["interactions"][0]["recording"]["redacted"])

    def test_write_and_credential_defaults_do_not_forward_requests(self):
        fixture = {
            "interactions": [
                {
                    "request": {"method": "POST", "path": "/change"},
                    "response": {"json": {"ok": True}},
                }
            ]
        }
        proxy, session = self.start(fixture)
        self.assertEqual(self.request(proxy.server_port, "POST", "/change", {})[0], 403)
        self.assertEqual(
            self.request(
                proxy.server_port,
                "GET",
                "/change",
                headers={"Authorization": "Bearer do-not-forward"},
            )[0],
            403,
        )
        captured = session.snapshot()
        self.assertEqual(captured["interactions"], [])
        self.assertEqual(captured["capture"]["error_count"], 2)
        self.assertNotIn("do-not-forward", json.dumps(captured))

    def test_origin_rejection_and_cors_headers_are_not_relayed(self):
        fixture = {
            "interactions": [
                {
                    "request": {"method": "GET", "path": "/"},
                    "response": {
                        "json": {"ok": True},
                        "headers": {"Access-Control-Allow-Origin": "*"},
                    },
                }
            ]
        }
        proxy, session = self.start(fixture)
        self.assertEqual(
            self.request(
                proxy.server_port,
                "GET",
                "/",
                headers={"Origin": "https://untrusted.example"},
            )[0],
            403,
        )
        status, _, headers = self.request(proxy.server_port, "GET", "/")
        self.assertEqual(status, 200)
        self.assertNotIn(
            "access-control-allow-origin", {key.lower() for key in headers}
        )
        self.assertFalse(session.snapshot()["capture"]["complete"])

    def test_payload_limit_marks_one_failure_and_rejects_partial_replay(self):
        fixture = {
            "interactions": [
                {
                    "request": {"method": "GET", "path": "/large"},
                    "response": {"json": {"value": "x" * 2000}},
                }
            ]
        }
        proxy, session = self.start(fixture, CapturePolicy(max_payload=1000))
        self.assertEqual(self.request(proxy.server_port, "GET", "/large")[0], 413)
        captured = session.snapshot()
        self.assertEqual(captured["capture"]["error_count"], 1)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            validate(captured)

