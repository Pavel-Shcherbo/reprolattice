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

