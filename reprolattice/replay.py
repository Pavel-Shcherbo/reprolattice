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


def redact(value):
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if key.casefold().replace("-", "_")
                in {x.replace("-", "_") for x in SECRET_KEYS}
                else redact(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


