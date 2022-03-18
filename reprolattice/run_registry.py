"""Immutable local run archives, indexed case outcomes and fenced named baselines."""

import json
import sqlite3
import time
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .jsonutil import strict_json
from .reports import write_reports
from .run_contract import (
    REPORT_LIMIT,
    REVISION,
    canonical,
    case_signatures,
    context,
    fingerprint,
    pair_key,
    sha,
    validate_run,
)
from .run_compare import comparison
from .suite_config import named

SCHEMA = """
CREATE TABLE metadata(singleton INTEGER PRIMARY KEY,store_id TEXT NOT NULL);
CREATE TABLE projects(name TEXT PRIMARY KEY,created_at TEXT NOT NULL);
CREATE TABLE runs(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,
 project TEXT NOT NULL REFERENCES projects(name),run_id TEXT NOT NULL,suite TEXT NOT NULL,
 revision TEXT NOT NULL,metadata TEXT NOT NULL,report BLOB NOT NULL,report_sha256 TEXT NOT NULL,
 recorded_at TEXT NOT NULL,UNIQUE(project,run_id));
CREATE TABLE cases(run TEXT NOT NULL REFERENCES runs(id),case_id TEXT NOT NULL,pair_key TEXT NOT NULL,
 source_id TEXT NOT NULL,status TEXT NOT NULL,duration REAL NOT NULL,input_sha256 TEXT NOT NULL,subject_sha256 TEXT NOT NULL,
 PRIMARY KEY(run,case_id),UNIQUE(run,pair_key));
CREATE TABLE requests(project TEXT NOT NULL REFERENCES projects(name),request_key TEXT NOT NULL,
 record_id TEXT NOT NULL REFERENCES runs(id),PRIMARY KEY(project,request_key));
CREATE TABLE baselines(project TEXT NOT NULL REFERENCES projects(name),name TEXT NOT NULL,
 record_id TEXT NOT NULL REFERENCES runs(id),generation INTEGER NOT NULL,updated_at TEXT NOT NULL,
 PRIMARY KEY(project,name));
CREATE TABLE baseline_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,project TEXT NOT NULL,name TEXT NOT NULL,
 previous_record TEXT,record_id TEXT NOT NULL REFERENCES runs(id),generation INTEGER NOT NULL,
 reason TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE INDEX runs_project_cursor ON runs(project,seq);
CREATE INDEX case_history ON cases(source_id,status,run);
"""


def now():
    return datetime.now(timezone.utc).isoformat()


class RunRegistry:
    def __init__(self, path, *, create=False):
        self.path = Path(path).expanduser()
        if self.path.is_symlink():
            raise ValueError("run registry cannot be a symlink")
        if not create and not self.path.is_file():
            raise ValueError("run registry does not exist; initialize it explicitly")
        if create:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self._connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 1} or version == 0 and not create:
                raise ValueError("unsupported run registry schema")
            if version == 0:
                db.execute("BEGIN IMMEDIATE")
                try:
                    version = db.execute("PRAGMA user_version").fetchone()[0]
                    if version not in {0, 1}:
                        raise ValueError("unsupported run registry schema")
                    if version == 0:
                        if db.execute(
                            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                        ).fetchone():
                            raise ValueError("refusing an unrelated SQLite database")
                        for statement in SCHEMA.split(";"):
                            if statement.strip():
                                db.execute(statement)
                        db.execute(
                            "INSERT INTO metadata VALUES(1,?)", (uuid.uuid4().hex,)
                        )
                        db.execute("PRAGMA user_version=1")
                        self.path.chmod(0o600)
                    db.commit()
                except BaseException:
                    db.rollback()
                    raise
            deadline = time.monotonic() + 10
            while True:
                try:
                    db.execute("PRAGMA journal_mode=WAL").fetchone()
                    break
                except sqlite3.OperationalError as error:
                    if (
                        getattr(error, "sqlite_errorcode", None)
                        not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
                        or time.monotonic() >= deadline
                    ):
                        raise
                    time.sleep(0.02)
            self.id = db.execute(
                "SELECT store_id FROM metadata WHERE singleton=1"
            ).fetchone()[0]

    @contextmanager
    def _connect(self):
        with closing(
            sqlite3.connect(self.path, timeout=10, isolation_level=None)
        ) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            yield db

