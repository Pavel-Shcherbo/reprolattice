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


