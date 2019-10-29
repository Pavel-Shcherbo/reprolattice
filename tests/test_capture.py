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

