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

