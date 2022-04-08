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

    @contextmanager
    def _tx(self, write=True):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def project(self, name):
        named(name, "project")
        with self._tx() as db:
            db.execute("INSERT OR IGNORE INTO projects VALUES(?,?)", (name, now()))
            return dict(
                db.execute("SELECT * FROM projects WHERE name=?", (name,)).fetchone()
            )

    def _project(self, db, name):
        named(name, "project")
        if (
            db.execute("SELECT name FROM projects WHERE name=?", (name,)).fetchone()
            is None
        ):
            raise ValueError("unknown registry project")

    def record(
        self, project, report, *, revision, request_key, label="", run_context=None
    ):
        named(request_key, "request key")
        validate_run(report)
        if not isinstance(revision, str) or not REVISION.fullmatch(revision):
            raise ValueError("revision requires a full lowercase 40/64-digit hash")
        if not isinstance(label, str) or len(label) > 256:
            raise ValueError("run label exceeds 256 characters")
        observed = context(
            report.get("execution_context", {}) if run_context is None else run_context
        )
        raw = canonical(report)
        report_sha = fingerprint(report)
        metadata = {
            "project": project,
            "revision": revision,
            "label": label,
            "context": observed,
            "report_sha256": report_sha,
            "run_id": report["run_id"],
            "suite": report["suite"],
            "passed": report["passed"],
            "full_suite": report["full_suite"],
            "counts": report["counts"],
        }
        record_id = fingerprint(metadata)
        with self._tx() as db:
            self._project(db, project)
            request = db.execute(
                "SELECT record_id FROM requests WHERE project=? AND request_key=?",
                (project, request_key),
            ).fetchone()
            if request and request["record_id"] != record_id:
                raise ValueError(
                    "request key conflicts with different run content or metadata"
                )
            prior = db.execute(
                "SELECT id FROM runs WHERE project=? AND run_id=?",
                (project, report["run_id"]),
            ).fetchone()
            if prior and prior["id"] != record_id:
                raise ValueError(
                    "run ID is already archived with different content or metadata"
                )
            existing = db.execute(
                "SELECT id FROM runs WHERE id=?", (record_id,)
            ).fetchone()
            if not existing:
                if (
                    db.execute(
                        "SELECT count(*) FROM runs WHERE project=?", (project,)
                    ).fetchone()[0]
                    >= 10000
                ):
                    raise ValueError("project exceeds 10,000 retained runs")
                db.execute(
                    "INSERT INTO runs(id,project,run_id,suite,revision,metadata,report,report_sha256,recorded_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        record_id,
                        project,
                        report["run_id"],
                        report["suite"],
                        revision,
                        canonical(metadata).decode(),
                        raw,
                        report_sha,
                        now(),
                    ),
                )
                for case in report["cases"]:
                    conditions, subject = case_signatures(case)
                    db.execute(
                        "INSERT INTO cases VALUES(?,?,?,?,?,?,?,?)",
                        (
                            record_id,
                            case["id"],
                            pair_key(case, modern=True),
                            case["source_id"],
                            case["status"],
                            case["duration_seconds"],
                            conditions,
                            subject,
                        ),
                    )
            db.execute(
                "INSERT OR IGNORE INTO requests VALUES(?,?,?)",
                (project, request_key, record_id),
            )
            result = self._get(db, project, record_id)
            result.pop("report")
            result["reused"] = existing is not None
            return result

    def _get(self, db, project, record_id):
        self._project(db, project)
        sha(record_id)
        row = db.execute(
            "SELECT * FROM runs WHERE project=? AND id=?", (project, record_id)
        ).fetchone()
        if row is None:
            raise ValueError("unknown archived run in this project")
        metadata = json.loads(row["metadata"])
        raw = bytes(row["report"])
        report = strict_json(raw, max_bytes=REPORT_LIMIT)
        validate_run(report)
        if (
            fingerprint(report) != row["report_sha256"]
            or metadata.get("report_sha256") != row["report_sha256"]
            or fingerprint(metadata) != record_id
            or metadata.get("project") != project
            or metadata.get("run_id") != row["run_id"]
            or metadata.get("suite") != row["suite"]
            or metadata.get("revision") != row["revision"]
            or report["run_id"] != row["run_id"]
            or report["suite"] != row["suite"]
        ):
            raise ValueError("archived run metadata/content identity mismatch")
        return {
            "id": record_id,
            "sequence": row["seq"],
            **metadata,
            "recorded_at": row["recorded_at"],
            "passed": report["passed"],
            "full_suite": report["full_suite"],
            "counts": report["counts"],
            "report": report,
        }

    def get(self, project, record_id):
        with self._tx(False) as db:
            return self._get(db, project, record_id)

    def list(self, project, *, after=0, limit=100, suite=None):
        if (
            type(after) is not int
            or after < 0
            or type(limit) is not int
            or not 1 <= limit <= 1000
        ):
            raise ValueError("invalid run cursor or page limit")
        if suite is not None:
            named(suite, "suite")
        with self._tx(False) as db:
            self._project(db, project)
            parameters = [project, after]
            condition = "project=? AND seq>?"
            if suite is not None:
                condition += " AND suite=?"
                parameters.append(suite)
            rows = db.execute(
                "SELECT id,seq,metadata,recorded_at FROM runs WHERE "
                + condition
                + " ORDER BY seq LIMIT ?",
                [*parameters, limit + 1],
            )
            items = []
            size = 0
            cursor = None
            for row in rows:
                item = {
                    "id": row["id"],
                    "sequence": row["seq"],
                    **json.loads(row["metadata"]),
                    "recorded_at": row["recorded_at"],
                }
                size += len(canonical(item))
                if len(items) >= limit or size > 4 * 1024 * 1024:
                    cursor = items[-1]["sequence"] if items else after
                    break
                items.append(item)
        return {
            "items": items,
            "next_cursor": cursor,
            "scope": "Metadata listing; use get/audit to verify archived payloads.",
        }

