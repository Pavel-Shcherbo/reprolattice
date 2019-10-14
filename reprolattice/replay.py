"""A loopback-only, ordered HTTP fixture server without upstream forwarding."""

import copy
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SECRET_KEYS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "password",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "x-api-key",
    "secret",
}


def secret_key(key):
    normalized = key.casefold().replace("-", "").replace("_", "")
    return normalized in {
        item.replace("-", "").replace("_", "") for item in SECRET_KEYS
    }


def redact(value):
    if isinstance(value, dict):
        return {
            key: ("[REDACTED]" if secret_key(key) else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def validate(fixture):
    if not isinstance(fixture, dict):
        raise ValueError("fixture must be an object")
    if (
        isinstance(fixture.get("capture"), dict)
        and fixture["capture"].get("complete") is False
    ):
        raise ValueError("incomplete capture cannot be verified as a complete scenario")
    interactions = fixture.get("interactions")
    if not isinstance(interactions, list) or not interactions:
        raise ValueError("interactions must be a non-empty list")
    for item in interactions:
        if not isinstance(item, dict):
            raise ValueError("each interaction must be an object")
        request, response = item.get("request", {}), item.get("response", {})
        if not isinstance(request, dict) or not isinstance(response, dict):
            raise ValueError("request and response must be objects")
        if request.get("method") not in {
            "GET",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
            "HEAD",
            "OPTIONS",
        }:
            raise ValueError("unsupported request method")
        if not isinstance(request.get("path"), str) or not request["path"].startswith(
            "/"
        ):
            raise ValueError("request path must start with /")
        status = response.get("status", 200)
        if type(status) is not int or not 200 <= status <= 599:
            raise ValueError("response status must be between 200 and 599")
        if status in {204, 304} and response.get("json") is not None:
            raise ValueError("204 and 304 responses cannot contain JSON bodies")
        if "body_length" in response:
            if (
                request["method"] != "HEAD"
                or type(response["body_length"]) is not int
                or response["body_length"] < 0
            ):
                raise ValueError(
                    "body_length is a nonnegative integer supported only for HEAD responses"
                )
        if not isinstance(response.get("headers", {}), dict):
            raise ValueError("response headers must be an object")
        for key, value in response.get("headers", {}).items():
            if (
                not isinstance(key, str)
                or not isinstance(value, str)
                or any(c in key + value for c in "\r\n")
            ):
                raise ValueError("invalid response header")
            if key.lower() in {"content-length", "transfer-encoding", "connection"}:
                raise ValueError("transport response headers are managed by the server")
        try:
            json.dumps(item, allow_nan=False)
        except (ValueError, TypeError) as error:
            raise ValueError("interaction must contain finite JSON values") from error
    return copy.deepcopy(interactions)


def make_server(fixture, port=0):
    interactions = validate(fixture)
    state = {"consumed": 0, "unexpected": 0, "total": len(interactions)}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, *_):
            pass

        def respond(self, status, body, headers=None, body_length=None):
            payload = b"" if status in {204, 304} else json.dumps(body).encode()
            self.send_response(status)
            if not any(key.lower() == "content-type" for key in (headers or {})):
                self.send_header("Content-Type", "application/json")
            self.send_header(
                "Content-Length",
                str(
                    body_length
                    if self.command == "HEAD" and body_length is not None
                    else len(payload)
                ),
            )
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)

        def handle_request(self):
            self.connection.settimeout(3)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if (
                    size < 0
                    or size > 1024 * 1024
                    or self.headers.get("Transfer-Encoding")
                ):
                    raise ValueError("unsupported request framing")
                raw = self.rfile.read(size)
                body = json.loads(raw) if raw else None
            except (ValueError, TimeoutError):
                with lock:
                    state["unexpected"] += 1
                self.respond(400, {"error": "expected bounded JSON body"})
                return
            with lock:
                item = (
                    interactions[state["consumed"]]
                    if state["consumed"] < len(interactions)
                    else None
                )
                expected = item["request"] if item else {}
                matches = (
                    item
                    and self.command == expected["method"]
                    and self.path == expected["path"]
                )
                if matches and "json" in expected:
                    matches = body == expected["json"]
                if matches:
                    state["consumed"] += 1
                    response = item["response"]
                else:
                    state["unexpected"] += 1
                    response = {
                        "status": 409,
                        "json": {
                            "error": "request does not match next fixture interaction"
                        },
                    }
            self.respond(
                response.get("status", 200),
                response.get("json"),
                response.get("headers"),
                response.get("body_length"),
            )

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = (
            handle_request
        )

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server, state
