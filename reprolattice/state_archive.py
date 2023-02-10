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
    pass
