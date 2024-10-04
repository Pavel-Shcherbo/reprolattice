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

    def complete(self, project, record, token):
        root = self.bundle(record)
        proof = verify_migration_bundle(root)
        if not proof["passed"]:
            raise ValueError("migration evidence has no complete replay")
        manifest = hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()
        report = strict_json(
            (root / "report.json").read_bytes(),
            max_bytes=8 * 1024 * 1024,
            max_nodes=1000000,
        )
        with self.transaction() as db:
            row = self.row(db, project, record)
            if (
                row["status"] not in ("running", "recovering")
                or row["token"] != token
                or row["lease_until"] <= self.now()
            ):
                raise ValueError("migration completion lost its ownership lease")
            inputs = json.loads(row["inputs"])
            actual = strict_json(
                (root / "plan.json").read_bytes(),
                max_bytes=4 * 1024 * 1024,
                max_nodes=250000,
            )
            if actual != inputs["plan"]:
                raise ValueError("migration bundle differs from reserved plan")
            # Validate the seed through a separate rehearsal; the retained baseline
            # must have the same exact logical source state, not merely the same SQL.
            from .migration_state import read_app_snapshot
            from .sqlite_seed import create_database
            import tempfile

            with tempfile.TemporaryDirectory(
                prefix="migration-seed-check-"
            ) as directory:
                seed_path = Path(directory) / "seed.sqlite"
                create_database(inputs["seed"], seed_path)
                if read_app_snapshot(seed_path)["sha256"] != report["source_snapshot"]:
                    raise ValueError("migration bundle differs from reserved seed")
            if row["lease_until"] <= self.now():
                raise ValueError("migration completion lease expired before commit")
            db.execute(
                "UPDATE rehearsals SET status='completed',generation=generation+1,token=NULL,lease_until=NULL,manifest_sha256=?,report=? WHERE id=?",
                (manifest, canonical(report).decode(), record),
            )
            return {
                "record": public(self.row(db, project, record)),
                "report": report,
                "plan": inputs["plan"],
            }

    def get(self, project, record):
        with self.transaction(False) as db:
            row = dict(self.row(db, project, record))
        result = {"record": public(row), "report": None}
        if row["status"] == "completed":
            root = self.bundle(record)
            files = inventory(root)
            manifest_path = root / "manifest.json"
            if (
                manifest_path.is_symlink()
                or not manifest_path.is_file()
                or manifest_path.stat().st_size > 65536
            ):
                raise ValueError("retained migration manifest is unsafe")
            raw = manifest_path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != row["manifest_sha256"]:
                raise ValueError(
                    "retained migration manifest differs from committed receipt"
                )
            manifest = strict_json(raw, max_bytes=65536)
            if set(manifest["files"]) != set(files):
                raise ValueError("retained migration inventory changed")
            for name, path in files.items():
                if manifest["files"][name] != {
                    "bytes": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }:
                    raise ValueError("retained migration file changed")
            report = json.loads(row["report"])
            if (
                strict_json(
                    files["report.json"].read_bytes(),
                    max_bytes=8 * 1024 * 1024,
                    max_nodes=1000000,
                )
                != report
            ):
                raise ValueError("retained migration report changed")
            result.update(
                report=report,
                plan=strict_json(
                    files["plan.json"].read_bytes(),
                    max_bytes=4 * 1024 * 1024,
                    max_nodes=250000,
                ),
            )
        return result

    def run(self, project, definition, seed, request_key, label=""):
        row, token = self.reserve(project, definition, seed, request_key, label)
        if token is None:
            return self.get(project, row["id"])
        qualify_migrations(definition, self.bundle(row["id"]), seed=seed)
        return self.complete(project, row["id"], token)

