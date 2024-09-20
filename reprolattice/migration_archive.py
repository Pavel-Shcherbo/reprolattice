"""Durable scoped rehearsal receipts with fenced completion and explicit recovery."""

from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time
import uuid

from .jsonutil import strict_json
from .migration_bundle import inventory, verify_migration_bundle
from .migration_model import compile_migrations
from .migration_runner import qualify_migrations
from .sqlite_seed import canonical, identity, compile_seed
from .suite_config import named

SCHEMA = """
CREATE TABLE IF NOT EXISTS rehearsals(
 sequence INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,
 project TEXT NOT NULL,request_key TEXT NOT NULL,input_sha256 TEXT NOT NULL,
 inputs TEXT NOT NULL,label TEXT NOT NULL,status TEXT NOT NULL,
 generation INTEGER NOT NULL,token TEXT,lease_until REAL,
 manifest_sha256 TEXT,report TEXT,created REAL NOT NULL,
 UNIQUE(project,request_key)
);
CREATE INDEX IF NOT EXISTS rehearsals_project ON rehearsals(project,sequence);
"""


def label_text(value):
    if (
        not isinstance(value, str)
        or len(value) > 128
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError("migration label requires at most 128 printable characters")
    return value


def run_id(value):
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError("invalid migration record ID")
    return value


def public(row):
    return {
        key: row[key]
        for key in (
            "sequence",
            "id",
            "project",
            "request_key",
            "input_sha256",
            "label",
            "status",
            "generation",
            "lease_until",
            "manifest_sha256",
            "created",
        )
    }


class MigrationArchive:
    def __init__(self, root, *, clock=None):
        self.root = Path(root)
        if self.root.is_symlink():
            raise ValueError("migration archive cannot be a symlink")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.root / "index.sqlite"
        self.clock = clock or time.time
        with self.transaction() as db:
            for sql in SCHEMA.split(";"):
                if sql.strip():
                    db.execute(sql)
        self.path.chmod(0o600)

    def now(self):
        value = self.clock()
        if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
            raise ValueError("invalid migration archive clock")
        return value

    @contextmanager
    def transaction(self, write=True):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def row(self, db, project, record):
        named(project, "migration project")
        run_id(record)
        row = db.execute(
            "SELECT * FROM rehearsals WHERE project=? AND id=?", (project, record)
        ).fetchone()
        if row is None:
            raise ValueError("migration record not found in this project")
        return row

    def list(self, project, *, after=0, limit=20):
        named(project, "migration project")
        if (
            type(after) is not int
            or after < 0
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise ValueError("invalid migration list cursor/limit")
        with self.transaction(False) as db:
            rows = db.execute(
                "SELECT * FROM rehearsals WHERE project=? AND sequence>? ORDER BY sequence LIMIT ?",
                (project, after, limit + 1),
            ).fetchall()
        return {
            "items": [public(r) for r in rows[:limit]],
            "next_cursor": rows[limit - 1]["sequence"] if len(rows) > limit else None,
        }

    def reserve(self, project, definition, seed, request_key, label=""):
        named(project, "migration project")
        named(request_key, "migration request key")
        label_text(label)
        plan = compile_migrations(definition)
        compiled = compile_seed(seed)
        inputs = {"plan": plan.definition, "seed": compiled, "label": label}
        digest = identity(inputs)
        now = self.now()
        with self.transaction() as db:
            prior = db.execute(
                "SELECT * FROM rehearsals WHERE project=? AND request_key=?",
                (project, request_key),
            ).fetchone()
            if prior is not None:
                if prior["input_sha256"] != digest:
                    raise ValueError(
                        "migration request key identifies different inputs"
                    )
                return public(prior), None
            if db.execute("SELECT count(*) FROM rehearsals").fetchone()[0] >= 1000:
                raise ValueError("migration archive has reached its 1,000-run capacity")
            record = identity({"nonce": str(uuid.uuid4())})
            token = str(uuid.uuid4())
            db.execute(
                "INSERT INTO rehearsals(id,project,request_key,input_sha256,inputs,label,status,generation,token,lease_until,created) VALUES(?,?,?,?,?,?,'running',1,?,?,?)",
                (
                    record,
                    project,
                    request_key,
                    digest,
                    canonical(inputs).decode(),
                    label,
                    token,
                    now + 600,
                    now,
                ),
            )
            return public(self.row(db, project, record)), token

    def bundle(self, record):
        run_id(record)
        path = self.root / record
        if path.is_symlink():
            raise ValueError("migration evidence directory cannot be a symlink")
        return path

