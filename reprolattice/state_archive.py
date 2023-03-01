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

    @contextmanager
    def _connect(self):
        with closing(
            sqlite3.connect(self.path, timeout=10, isolation_level=None)
        ) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA trusted_schema=OFF")
            yield db

    @contextmanager
    def _transaction(self, write=False):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def record(
        self, project, document, *, request_key, label="", request_fingerprint=None
    ):
        named(project, "state project")
        named(request_key, "state request key")
        if (
            not isinstance(label, str)
            or len(label) > 128
            or any(ord(char) < 32 for char in label)
        ):
            raise ValueError("state label must be at most 128 printable characters")
        validate_evidence(document)
        request_fingerprint = sha(request_fingerprint or document["sha256"])
        raw = canonical(document)
        summary = evidence_summary(document)
        with self._transaction(True) as db:
            existing = db.execute(
                "SELECT record,fingerprint FROM state_requests WHERE project=? AND request_key=?",
                (project, request_key),
            ).fetchone()
            if existing:
                row = db.execute(
                    "SELECT * FROM state_runs WHERE project=? AND id=?",
                    (project, existing[0]),
                ).fetchone()
                if (
                    row is None
                    or existing["fingerprint"] != request_fingerprint
                    or row["id"] != document["sha256"]
                    or row["label"] != label
                ):
                    raise ValueError(
                        "state request key conflicts with different evidence or label"
                    )
                return self._read(db, project, row["id"])["record"]
            row = db.execute(
                "SELECT * FROM state_runs WHERE id=?", (document["sha256"],)
            ).fetchone()
            if row is not None:
                if (
                    row["project"] != project
                    or row["label"] != label
                    or bytes(row["document"]) != raw
                ):
                    raise ValueError(
                        "state evidence already belongs to another project or label"
                    )
                self._read(db, project, row["id"])
            else:
                if db.execute(
                    "SELECT 1 FROM state_runs WHERE project=? AND run_id=?",
                    (project, document["report"]["run_id"]),
                ).fetchone():
                    raise ValueError("run ID already has different retained evidence")
                size, count = db.execute(
                    "SELECT coalesce(sum(length(document)),0),count(*) FROM state_runs"
                ).fetchone()
                if size + len(raw) > MAX_STORE or count >= 500:
                    raise ValueError(
                        "state archive exceeds 256 MiB or 500 runs; use another archive"
                    )
                recorded = datetime.now(timezone.utc).isoformat()
                db.execute(
                    "INSERT INTO state_runs(id,project,run_id,label,recorded_at,summary,document) VALUES(?,?,?,?,?,?,?)",
                    (
                        document["sha256"],
                        project,
                        document["report"]["run_id"],
                        label,
                        recorded,
                        canonical(summary),
                        raw,
                    ),
                )
            if db.execute("SELECT count(*) FROM state_requests").fetchone()[0] >= 2000:
                raise ValueError("state archive exceeds 2,000 idempotency requests")
            db.execute(
                "INSERT INTO state_requests VALUES(?,?,?,?)",
                (project, request_key, document["sha256"], request_fingerprint),
            )
            return self._header(
                db.execute(
                    "SELECT * FROM state_runs WHERE id=?", (document["sha256"],)
                ).fetchone()
            )

    def requested(self, project, request_key, request_fingerprint, label=""):
        named(project, "state project")
        named(request_key, "state request key")
        sha(request_fingerprint)
        with self._transaction() as db:
            row = db.execute(
                "SELECT record,fingerprint FROM state_requests WHERE project=? AND request_key=?",
                (project, request_key),
            ).fetchone()
            if row is None:
                return None
            stored = self._read(db, project, row["record"])
            if (
                row["fingerprint"] != request_fingerprint
                or stored["record"]["label"] != label
            ):
                raise ValueError(
                    "state request key conflicts with different controls or label"
                )
            return stored

    def _header(self, row):
        value = strict_json(row["summary"], max_bytes=256 * 1024)
        if value.get("id") != row["id"] or value.get("run_id") != row["run_id"]:
            raise ValueError("state archive summary identity mismatch")
        return {
            **value,
            "sequence": row["seq"],
            "label": row["label"],
            "recorded_at": row["recorded_at"],
            "project": row["project"],
        }

    def _read(self, db, project, record):
        row = db.execute(
            "SELECT seq,id,project,run_id,label,recorded_at,summary,length(document) AS bytes FROM state_runs WHERE project=? AND id=?",
            (project, record),
        ).fetchone()
        if row is None:
            raise ValueError("unknown retained state run in this project")
        if row["bytes"] > MAX_EVIDENCE:
            raise ValueError("stored state evidence exceeds byte budget")
        raw = db.execute(
            "SELECT substr(document,1,?) FROM state_runs WHERE project=? AND id=?",
            (MAX_EVIDENCE + 1, project, record),
        ).fetchone()[0]
        document = strict_json(raw, max_bytes=MAX_EVIDENCE, max_nodes=1800000)
        validate_evidence(document)
        if document["sha256"] != row["id"] or canonical(
            evidence_summary(document)
        ) != bytes(row["summary"]):
            raise ValueError("stored state evidence/index mismatch")
        return {"record": self._header(row), "document": document}

    def get(self, project, record):
        named(project, "state project")
        sha(record)
        with self._transaction() as db:
            return self._read(db, project, record)

    def list(self, project, *, after=0, limit=25):
        named(project, "state project")
        cursor(after)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("state archive list limit must be 1–100")
        with self._transaction() as db:
            rows = db.execute(
                "SELECT seq,id,project,run_id,label,recorded_at,summary FROM state_runs WHERE project=? AND (?=0 OR seq<?) ORDER BY seq DESC LIMIT ?",
                (project, after, after, limit + 1),
            ).fetchall()
            items = [self._header(row) for row in rows[:limit]]
            return {
                "items": items,
                "next_cursor": items[-1]["sequence"] if len(rows) > limit else None,
            }

