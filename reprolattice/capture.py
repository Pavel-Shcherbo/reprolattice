"""Explicit HTTP/JSON capture against one pinned upstream origin."""

import copy
import argparse
import http.client
import ipaddress
import json
import math
import os
import socket
import tempfile
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .replay import redact, secret_key

HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class CaptureFailure(Exception):
    def __init__(self, kind, message, status=502):
        super().__init__(message)
        self.kind, self.message, self.status = kind, message, status
        self.recorded = False


@dataclass(frozen=True)
class CapturePolicy:
    allow_remote: bool = False
    allow_writes: bool = False
    allow_credentials: bool = False
    timeout: float = 5
    max_payload: int = 256 * 1024
    max_bytes: int = 8 * 1024 * 1024
    max_interactions: int = 1000
    max_parallel: int = 8

    def __post_init__(self):
        for value in [self.allow_remote, self.allow_writes, self.allow_credentials]:
            if type(value) is not bool:
                raise ValueError("capture policy switches must be boolean")
        if (
            type(self.timeout) not in (int, float)
            or not math.isfinite(self.timeout)
            or not 0 < self.timeout <= 30
        ):
            raise ValueError("capture timeout must be between zero and 30 seconds")
        for name, maximum in [
            ("max_payload", 1024 * 1024),
            ("max_bytes", 64 * 1024 * 1024),
            ("max_interactions", 10000),
            ("max_parallel", 32),
        ]:
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"{name} must be between 1 and {maximum}")


def scrub_url(value):
    try:
        parts = urlsplit(value)
        parsed = parse_qsl(parts.query, keep_blank_values=True)
    except ValueError:
        return "[INVALID URL]"
    if parts.username is None and not any(secret_key(key) for key, _ in parsed):
        return value
    pairs = [(key, "[REDACTED]" if secret_key(key) else item) for key, item in parsed]
    netloc = parts.netloc
    if parts.username is not None:
        host = parts.hostname or ""
        netloc = (f"[{host}]" if ":" in host else host) + (
            f":{parts.port}" if parts.port else ""
        )
    return urlunsplit(
        (parts.scheme, netloc, parts.path, urlencode(pairs), parts.fragment)
    )


def stored_headers(headers):
    result = redact(dict(headers))
    for name, value in list(result.items()):
        if name.casefold() in {"location", "referer", "referrer"}:
            result[name] = scrub_url(value)
    return result


def transport_headers(headers):
    blocked = set(HOP_HEADERS)
    for name, value in headers:
        if name.casefold() == "connection":
            blocked.update(item.strip().casefold() for item in value.split(","))
    result = {}
    seen = set()
    for name, value in headers:
        if (
            name.casefold() in blocked
            or name.casefold() == "accept-encoding"
            or name.casefold().startswith("access-control-")
        ):
            continue
        if "\r" in name + value or "\n" in name + value:
            raise CaptureFailure(
                "headers", "folded or multiline headers are unsupported", 502
            )
        if name.casefold() in seen:
            raise CaptureFailure(
                "headers", "duplicate header fields require an explicit adapter", 502
            )
        seen.add(name.casefold())
        result[name] = value
    if sum(len(key) + len(value) for key, value in result.items()) > 16384:
        raise CaptureFailure(
            "limit", "upstream or request headers exceed the capture limit", 413
        )
    return result


def strict_json(payload):
    def reject(value):
        raise ValueError(f"nonstandard JSON constant: {value}")

    try:
        result = json.loads(payload, parse_constant=reject)
    except RecursionError as error:
        raise ValueError("JSON nesting exceeds the capture limit") from error
    pending = [(result, 0)]
    nodes = 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if depth > 100 or nodes > 100000:
            raise ValueError("JSON structure exceeds the capture budget")
        if isinstance(value, dict):
            pending.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            pending.extend((item, depth + 1) for item in value)
    return result


class CaptureSession:
    def __init__(self, upstream, policy=None, name="recorded-scenario"):
        if policy is not None and not isinstance(policy, CapturePolicy):
            raise ValueError("policy must be a CapturePolicy")
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValueError("scenario name must contain 1 to 200 characters")
        if not isinstance(upstream, str) or len(upstream) > 8192:
            raise ValueError("upstream must be a URL of at most 8192 characters")
        self.policy = policy or CapturePolicy()
        self.name = name
        parts = urlsplit(upstream)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.query
            or parts.fragment
        ):
            raise ValueError(
                "upstream must be an HTTP(S) origin with an optional path prefix, without credentials, query or fragment"
            )
        try:
            parts.port
        except ValueError as error:
            raise ValueError("upstream port is invalid") from error
        local = parts.hostname.casefold() == "localhost"
        try:
            local = local or ipaddress.ip_address(parts.hostname).is_loopback
        except ValueError:
            pass
        if not local and not self.policy.allow_remote:
            raise ValueError("remote upstreams require explicit allow_remote")
        self.upstream = parts
        self._lock = threading.Lock()
        self._idle = threading.Condition(self._lock)
        self._sequence = 0
        self._pending = {}
        self._records = {}
        self._errors = []
        self._error_count = 0
        self._bytes = 0
        self._concurrent = False
        self._slots = threading.BoundedSemaphore(self.policy.max_parallel)

    def begin(self, request):
        reserve = self.policy.max_payload * 2 + 32768
        with self._lock:
            if len(self._records) + len(self._pending) >= self.policy.max_interactions:
                raise CaptureFailure("limit", "interaction limit reached", 429)
            if self._bytes + (len(self._pending) + 1) * reserve > self.policy.max_bytes:
                raise CaptureFailure("limit", "capture byte budget exhausted", 429)
            self._sequence += 1
            sequence = self._sequence
            if self._pending:
                self._concurrent = True
            self._pending[sequence] = copy.deepcopy(request)
            return sequence

    def complete(self, sequence, response, elapsed, redacted):
        with self._lock:
            request = self._pending[sequence]
            interaction = {
                "request": request,
                "response": response,
                "recording": {
                    "sequence": sequence,
                    "elapsed_ms": round(elapsed * 1000, 3),
                    "redacted": redacted,
                },
            }
            size = len(json.dumps(interaction, allow_nan=False).encode())
            if self._bytes + size > self.policy.max_bytes:
                raise CaptureFailure(
                    "limit", "serialized capture exceeded the byte budget", 429
                )
            self._pending.pop(sequence)
            self._records[sequence] = interaction
            self._bytes += size
            self._idle.notify_all()

    def fail(self, kind, path, sequence=None):
        with self._lock:
            if sequence is not None:
                self._pending.pop(sequence, None)
            self._error_count += 1
            if len(self._errors) < 50:
                self._errors.append({"kind": kind, "path": scrub_url(path)})
            self._idle.notify_all()

    def wait_idle(self, timeout):
        with self._idle:
            return self._idle.wait_for(lambda: not self._pending, timeout=timeout)

    def snapshot(self):
        with self._lock:
            complete = (
                bool(self._records) and not self._pending and self._error_count == 0
            )
            return {
                "name": self.name,
                "interactions": copy.deepcopy(
                    [self._records[key] for key in sorted(self._records)]
                ),
                "capture": {
                    "complete": complete,
                    "requires_review": True,
                    "upstream": scrub_url(self.upstream.geturl()),
                    "active_requests": len(self._pending),
                    "error_count": self._error_count,
                    "errors": copy.deepcopy(self._errors),
                    "stored_bytes": self._bytes,
                    "concurrent_requests_observed": self._concurrent,
                    "scope": "Ordered HTTP/JSON interactions. Original byte formatting, application state and concurrent scheduling are not reproduced. Review paths, payloads and redacted fields before sharing or testing.",
                },
            }

    def save(self, path, overwrite=False):
        snapshot = self.snapshot()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(snapshot, indent=2, allow_nan=False).encode()
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=path.parent, prefix=".capture-", delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if overwrite:
                os.replace(temporary, path)
                temporary = None
            else:
                os.link(temporary, path)
            return snapshot["capture"]
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _forward(self, method, path, headers, raw):
        if method not in SAFE_METHODS and (
            method not in WRITE_METHODS or not self.policy.allow_writes
        ):
            raise CaptureFailure(
                "method", "write methods require explicit allow_writes", 403
            )
        if not path.startswith("/") or path.startswith("//") or urlsplit(path).scheme:
            raise CaptureFailure("path", "use an origin-relative request path", 400)
        if (
            len(path) > 8192
            or sum(len(key) + len(value) for key, value in headers) > 16384
        ):
            raise CaptureFailure(
                "limit", "request path or headers exceed the capture limit", 413
            )
        try:
            parsed = strict_json(raw) if raw else None
        except (ValueError, UnicodeError) as error:
            raise CaptureFailure(
                "request_json", "capture accepts JSON request bodies only", 415
            ) from error
        kept_headers = transport_headers(headers)
        safe_headers = stored_headers(kept_headers)
        safe_path = scrub_url(path)
        safe_body = redact(parsed)
        request = {"method": method, "path": safe_path, "headers": safe_headers}
        if raw:
            request["json"] = safe_body
        sensitive = (
            safe_path != path or safe_headers != kept_headers or safe_body != parsed
        )
        if sensitive and not self.policy.allow_credentials:
            raise CaptureFailure(
                "credentials",
                "credential-bearing requests require explicit allow_credentials",
                403,
            )
        sequence = self.begin(request)
        started = time.monotonic()
        connection = None
        timer = None
        socket_holder = [None]
        try:
            connection_type = (
                http.client.HTTPSConnection
                if self.upstream.scheme == "https"
                else http.client.HTTPConnection
            )
            connection = connection_type(
                self.upstream.hostname, self.upstream.port, timeout=self.policy.timeout
            )

            def interrupt():
                client_socket = socket_holder[0]
                if client_socket is not None:
                    try:
                        client_socket.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                connection.close()

            timer = threading.Timer(self.policy.timeout, interrupt)
            timer.daemon = True
            timer.start()
            target = self.upstream.path.rstrip("/") + path
            forwarded = dict(kept_headers)
            forwarded["Accept-Encoding"] = "identity"
            connection.request(method, target, body=raw or None, headers=forwarded)
            socket_holder[0] = connection.sock
            response = connection.getresponse()
            response_headers = transport_headers(response.getheaders())
            payload = bytearray()
            while True:
                if time.monotonic() - started > self.policy.timeout:
                    raise TimeoutError("capture deadline exceeded")
                chunk = response.read1(
                    min(8192, self.policy.max_payload + 1 - len(payload))
                )
                if not chunk:
                    break
                payload.extend(chunk)
                if len(payload) > self.policy.max_payload:
                    raise CaptureFailure(
                        "limit", "upstream response exceeds the payload limit", 413
                    )
            try:
                body = (
                    strict_json(payload)
                    if method != "HEAD" and response.status not in {204, 304}
                    else None
                )
            except (ValueError, UnicodeError) as error:
                raise CaptureFailure(
                    "response_json", "upstream response is not supported JSON", 502
                ) from error
            sanitized_headers = stored_headers(response_headers)
            safe_response = {
                "status": response.status,
                "json": redact(body),
                "headers": sanitized_headers,
            }
            if method == "HEAD":
                declared = response.getheader("Content-Length", "0")
                safe_response["body_length"] = (
                    int(declared) if declared.isdigit() else 0
                )
            changed = (
                sensitive
                or safe_response["json"] != body
                or sanitized_headers != response_headers
            )
            self.complete(sequence, safe_response, time.monotonic() - started, changed)
            return (
                response.status,
                response_headers,
                bytes(payload),
                safe_response.get("body_length"),
            )
        except CaptureFailure as error:
            self.fail(error.kind, path, sequence)
            error.recorded = True
            raise
        except (OSError, http.client.HTTPException, ValueError, UnicodeError) as error:
            self.fail("upstream", path, sequence)
            failure = CaptureFailure(
                "upstream", "upstream request failed or exceeded its deadline", 502
            )
            failure.recorded = True
            raise failure from error
        finally:
            if timer is not None:
                timer.cancel()
            if connection is not None:
                connection.close()
            with self._lock:
                pending = sequence in self._pending
            if pending:
                self.fail("incomplete_upstream", path, sequence)


def make_capture_server(upstream, policy=None, port=0, name="recorded-scenario"):
    session = CaptureSession(upstream, policy, name)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, *_):
            pass

        def handle_request(self):
            allowed = {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }
            origin = self.headers.get("Origin")
            if (
                self.headers.get("Host") not in allowed
                or (origin and origin not in {f"http://{host}" for host in allowed})
                or self.headers.get("Sec-Fetch-Site") == "cross-site"
            ):
                session.fail("origin", self.path)
                self.reply_error(
                    CaptureFailure("origin", "capture accepts local requests only", 403)
                )
                return
            if not session._slots.acquire(blocking=False):
                session.fail("parallel_limit", self.path)
                self.reply_error(
                    CaptureFailure(
                        "parallel_limit", "capture concurrency limit reached", 429
                    )
                )
                return
            try:
                self.connection.settimeout(session.policy.timeout)
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if (
                        size < 0
                        or size > session.policy.max_payload
                        or self.headers.get("Transfer-Encoding")
                    ):
                        raise CaptureFailure(
                            "request_limit",
                            "unsupported request framing or payload size",
                            413,
                        )
                    raw = self.rfile.read(size)
                    if len(raw) != size:
                        raise CaptureFailure(
                            "request_body",
                            "request body ended before its declared length",
                            400,
                        )
                    status, headers, payload, head_length = session._forward(
                        self.command, self.path, list(self.headers.items()), raw
                    )
                    self.send_response_only(status)
                    for key, value in headers.items():
                        self.send_header(key, value)
                    self.send_header(
                        "Content-Length",
                        str(
                            head_length
                            if self.command == "HEAD" and head_length is not None
                            else len(payload)
                        ),
                    )
                    self.send_header("Connection", "close")
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(payload)
                except CaptureFailure as error:
                    if not error.recorded:
                        session.fail(error.kind, self.path)
                    self.reply_error(error)
                except (OSError, ValueError):
                    session.fail("request_transport", self.path)
            finally:
                session._slots.release()

        def reply_error(self, error):
            body = json.dumps({"error": error.kind, "message": error.message}).encode()
            try:
                self.send_response(error.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)
            except OSError:
                pass

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = (
            do_TRACE
        ) = do_CONNECT = handle_request

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server, session


def main():
    parser = argparse.ArgumentParser(
        description="Capture HTTP/JSON calls sent to one explicitly configured upstream"
    )
    parser.add_argument("upstream")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--allow-writes", action="store_true")
    parser.add_argument("--allow-credentials", action="store_true")
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        if args.output.exists() and not args.overwrite:
            raise ValueError(
                "output already exists; choose a new path or explicitly use --overwrite"
            )
        if args.duration is not None and (
            not math.isfinite(args.duration) or not 0 < args.duration <= 3600
        ):
            raise ValueError("capture duration must be between zero and 3600 seconds")
        policy = CapturePolicy(
            allow_remote=args.allow_remote,
            allow_writes=args.allow_writes,
            allow_credentials=args.allow_credentials,
            timeout=args.timeout,
        )
        server, session = make_capture_server(args.upstream, policy, args.port)
    except (ValueError, OSError) as error:
        parser.exit(2, f"{error}\n")
    timer = None
    if args.duration is not None:
        timer = threading.Timer(args.duration, server.shutdown)
        timer.daemon = True
        timer.start()
    print(
        json.dumps(
            {
                "listening": f"http://127.0.0.1:{server.server_port}",
                "upstream": args.upstream,
                "output": str(args.output),
            }
        ),
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        if timer is not None:
            timer.cancel()
        server.server_close()
    session.wait_idle(policy.timeout + 1)
    try:
        metadata = session.save(args.output, overwrite=args.overwrite)
    except (ValueError, OSError) as error:
        parser.exit(2, f"could not save capture: {error}\n")
    print(json.dumps({"output": str(args.output), **metadata}, indent=2))
    return 0 if metadata["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
