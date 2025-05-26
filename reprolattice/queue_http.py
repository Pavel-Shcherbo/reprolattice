"""Loopback-only JSON queue fixture; unsupported wire attempts remain visible."""

import hmac
import json
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from .jsonutil import strict_json
from .queue_engine import QueueCapacity, QueueEngine


def make_queue_server(configuration):
    engine = QueueEngine(configuration)
    token = secrets.token_urlsafe(32)
    wire = {"errors": 0, "accepted": 0}
    wire_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(2)
            self.accounted = False
            with wire_lock:
                wire["accepted"] += 1
            self.deadline = threading.Timer(2, self.expire_connection)
            self.deadline.daemon = True
            self.deadline.start()

        def expire_connection(self):
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        def finish(self):
            self.deadline.cancel()
            try:
                super().finish()
            finally:
                if not self.accounted:
                    with wire_lock:
                        wire["errors"] += 1

        def log_message(self, *_):
            pass

        def respond(self, status, value):
            self.accounted = True
            raw = json.dumps(value, allow_nan=False).encode()
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                # Delivery may already have committed; retaining the command is
                # essential for an honest lost-response/redelivery diagnosis.
                pass

        def reject(self, status, message):
            with wire_lock:
                wire["errors"] += 1
            self.respond(status, {"error": message})

        def send_error(self, code, message=None, explain=None):
            self.reject(code, message or "unsupported queue wire request")

        def do_POST(self):
            expected_host = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != expected_host or self.headers.get("Origin"):
                self.reject(
                    403,
                    "queue fixture accepts its exact loopback host and no browser Origin",
                )
                return
            supplied = self.headers.get("X-Queue-Fixture", "")
            if not hmac.compare_digest(supplied.encode(), token.encode()):
                self.reject(403, "queue fixture capability is missing or invalid")
                return
            if self.path != "/command":
                self.reject(404, "queue fixture supports POST /command only")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 131072 or self.headers.get("Transfer-Encoding"):
                    raise ValueError(
                        "queue command requires at most 128 KiB JSON bytes"
                    )
                if (
                    self.headers.get("Content-Type", "").split(";")[0]
                    != "application/json"
                ):
                    raise ValueError("queue command requires application/json")
                self.connection.settimeout(2)
                command = strict_json(
                    self.rfile.read(length), max_bytes=131072, max_nodes=11000
                )
                response = engine.execute(command)
            except QueueCapacity as error:
                self.reject(429, str(error))
                return
            except (ValueError, OSError, TimeoutError) as error:
                self.reject(400, str(error))
                return
            self.respond(response["status"], response["body"])

        def do_GET(self):
            self.reject(405, "queue fixture requires POST /command")

        do_PUT = do_GET
        do_DELETE = do_GET
        do_PATCH = do_GET
        do_HEAD = do_GET
        do_OPTIONS = do_GET

    # Serial handling gives every worker command one linearization point, and
    # shutdown waits for the current bounded handler before evidence is captured.
    server = HTTPServer(("127.0.0.1", 0), Handler)
    return server, engine, token, wire
