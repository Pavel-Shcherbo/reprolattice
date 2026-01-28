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


def verify_export(value):
    fields(value, ("format", "session", "document", "sha256"))
    if value["format"] != FORMAT or value["sha256"] != fingerprint(
        {k: v for k, v in value.items() if k != "sha256"}
    ):
        raise ValueError("saved queue export identity differs")
    meta = value["session"]
    fields(
        meta,
        (
            "id",
            "project",
            "label",
            "kind",
            "generation",
            "created",
            "parent",
            "document_sha256",
        ),
    )
    identity(meta["id"])
    name(meta["project"], "queue project")
    label(meta["label"])
    integer(meta["generation"], "generation", 1)
    integer(meta["created"], "created", 0, 9223372036854775807)
    if meta["parent"] is not None:
        fields(meta["parent"], ("id", "generation", "document_sha256"))
        identity(meta["parent"]["id"])
        integer(meta["parent"]["generation"], "parent generation", 1)
        if (
            not isinstance(meta["parent"]["document_sha256"], str)
            or len(meta["parent"]["document_sha256"]) != 64
        ):
            raise ValueError("invalid parent content identity")
    if meta["document_sha256"] != fingerprint(value["document"]):
        raise ValueError("saved queue document identity differs")
    proof = checked_document(meta["kind"], value["document"])
    return {
        "passed": True,
        "kind": meta["kind"],
        "generation": meta["generation"],
        "replay": proof,
        "source_authenticated": False,
        "application_reexecuted": False,
        "parent_authenticated": False,
    }


class QueueLab:
    pass
