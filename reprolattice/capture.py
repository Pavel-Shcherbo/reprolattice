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

