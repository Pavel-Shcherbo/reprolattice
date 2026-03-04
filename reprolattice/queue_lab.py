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
    def __init__(self, path):
        self.path = Path(path)
        if self.path.is_symlink():
            raise ValueError("queue lab database cannot be a symlink")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        new = not self.path.exists()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("unsupported queue lab schema")
            if version == 0:
                if db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchone():
                    raise ValueError("refusing an unrelated queue lab database")
                for sql in (
                    "CREATE TABLE sessions(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,project TEXT NOT NULL,metadata BLOB NOT NULL,metadata_sha TEXT NOT NULL,document BLOB NOT NULL)",
                    "CREATE INDEX scoped_queue_sessions ON sessions(project,seq)",
                    "CREATE TABLE receipts(project TEXT NOT NULL,request_key TEXT NOT NULL,input_sha TEXT NOT NULL,response BLOB NOT NULL,response_sha TEXT NOT NULL,PRIMARY KEY(project,request_key))",
                ):
                    db.execute(sql)
                db.execute("PRAGMA user_version=1")
        if new:
            os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def unpack(row):
        meta = strict_json(row["metadata"], max_bytes=16384)
        if (
            fingerprint(meta) != row["metadata_sha"]
            or meta["id"] != row["id"]
            or meta["project"] != row["project"]
        ):
            raise ValueError("saved queue metadata identity differs")
        document = strict_json(
            row["document"], max_bytes=MAX_DOCUMENT, max_nodes=4000000
        )
        if meta["document_sha256"] != fingerprint(document):
            raise ValueError("saved queue content identity differs")
        proof = checked_document(meta["kind"], document)
        return meta, document, proof

    @staticmethod
    def row(db, project, record):
        identity(record)
        row = db.execute(
            "SELECT * FROM sessions WHERE project=? AND id=?", (project, record)
        ).fetchone()
        if row is None:
            raise ValueError("queue session not found in this project")
        return row

    @staticmethod
    def fence(meta, generation):
        integer(generation, "generation", 1)
        if generation != meta["generation"]:
            raise ValueError("queue generation changed; refresh the saved view")

    def list(self, project, *, before=0, limit=25):
        name(project, "queue project")
        integer(before, "list cursor", 0, 9223372036854775807)
        integer(limit, "list limit", 1, 100)
        with self.connect() as db:
            rows = db.execute(
                "SELECT seq,id,project,metadata,metadata_sha FROM sessions WHERE project=? AND (?=0 OR seq<?) ORDER BY seq DESC LIMIT ?",
                (project, before, before, limit + 1),
            ).fetchall()
            items = []
            for row in rows[:limit]:
                meta = strict_json(row["metadata"], max_bytes=16384)
                if (
                    fingerprint(meta) != row["metadata_sha"]
                    or meta["id"] != row["id"]
                    or meta["project"] != project
                ):
                    raise ValueError("queue list metadata identity differs")
                items.append({**meta, "sequence": row["seq"]})
            return {
                "items": items,
                "next_cursor": rows[limit - 1]["seq"] if len(rows) > limit else None,
            }

