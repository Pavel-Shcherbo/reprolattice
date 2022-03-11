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


