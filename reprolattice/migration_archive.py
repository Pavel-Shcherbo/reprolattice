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


