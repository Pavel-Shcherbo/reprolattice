"""Transactional saved queue simulations with scoped, input-bound retry receipts."""

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import time
import uuid

from .jsonutil import strict_json, validate_json
from .queue_controls import run_worker_control, verify_worker_control
from .queue_engine import QueueEngine, verify_queue_evidence
from .queue_model import canonical, configuration, fields, fingerprint, integer, name

MAX_DOCUMENT = 24 * 1024 * 1024
MAX_RETAINED = 256 * 1024 * 1024
MAX_SESSIONS = 1000
MAX_RECEIPTS = 10000
FORMAT = "reprolattice.saved-queue.v1"


def identity(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError("queue session requires a canonical UUID")
    return value


def label(value):
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 128
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError("queue label requires 1–128 printable characters")
    return value


def checked_document(kind, value):
    validate_json(value, max_bytes=MAX_DOCUMENT, max_nodes=4000000)
    if kind == "workers":
        return verify_worker_control(value)
    if kind not in ("simulation", "imported"):
        raise ValueError("unknown retained queue kind")
    return verify_queue_evidence(value)


