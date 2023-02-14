"""Transactional local archive of bounded immutable state evidence documents."""

from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from .jsonutil import strict_json
from .run_contract import sha
from .sqlite_seed import canonical
from .state_evidence import MAX_EVIDENCE, evidence_summary, validate_evidence
from .suite_config import named

SCHEMA = """
CREATE TABLE state_meta(singleton INTEGER PRIMARY KEY,kind TEXT NOT NULL);
CREATE TABLE state_runs(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,
 project TEXT NOT NULL,run_id TEXT NOT NULL,label TEXT NOT NULL,recorded_at TEXT NOT NULL,
 summary BLOB NOT NULL,document BLOB NOT NULL,UNIQUE(project,run_id));
CREATE TABLE state_requests(project TEXT NOT NULL,request_key TEXT NOT NULL,
 record TEXT NOT NULL REFERENCES state_runs(id),fingerprint TEXT NOT NULL,PRIMARY KEY(project,request_key));
CREATE INDEX state_project_cursor ON state_runs(project,seq);
"""
MAX_STORE = 256 * 1024 * 1024


def cursor(value):
    if type(value) is not int or not 0 <= value <= 9223372036854775807:
        raise ValueError("state archive cursor must be a bounded nonnegative integer")
    return value


class StateArchive:
    def __init__(self, path, *, create=False):
        self.path = Path(path)
        if self.path.is_symlink() or not create and not self.path.is_file():
            raise ValueError(
                "state archive requires an existing ordinary file or explicit initialization"
            )
        for suffix in ("-wal", "-shm", "-journal"):
            if Path(str(self.path) + suffix).is_symlink():
                raise ValueError("state archive sidecar symlinks are unsupported")
        if create:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version == 0 and create:
                    if db.execute(
                        "SELECT name FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'"
                    ).fetchone():
                        raise ValueError("refusing an unrelated database")
                    for statement in SCHEMA.split(";"):
                        if statement.strip():
                            db.execute(statement)
                    db.execute(
                        "INSERT INTO state_meta VALUES(1,'reprolattice.state-archive.v1')"
                    )
                    db.execute("PRAGMA user_version=1")
                    self.path.chmod(0o600)
                elif version != 1:
                    raise ValueError("unsupported state archive schema")
                marker = db.execute(
                    "SELECT kind FROM state_meta WHERE singleton=1"
                ).fetchone()
                if marker is None or marker[0] != "reprolattice.state-archive.v1":
                    raise ValueError("unsupported state archive identity")
                db.commit()
            except BaseException:
                db.rollback()
                raise
            db.execute("PRAGMA journal_mode=WAL")

