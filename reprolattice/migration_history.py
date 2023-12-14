"""Protected, deterministic history committed with each isolated schema change."""

import json

from .migration_model import PREFIX
from .sqlite_seed import canonical, identity

STACK = PREFIX + "migration_stack"
EVENTS = PREFIX + "migration_events"


def initialize_history(db):
    if db.execute(
        "SELECT name FROM sqlite_schema WHERE lower(name) GLOB '_reprolattice_*'"
    ).fetchone():
        raise ValueError("migration source contains reserved rehearsal metadata")
    db.execute(
        "CREATE TABLE "
        + STACK
        + "(position INTEGER PRIMARY KEY,migration TEXT UNIQUE NOT NULL,step_sha256 TEXT NOT NULL,before_sha256 TEXT NOT NULL,after_sha256 TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE "
        + EVENTS
        + "(seq INTEGER PRIMARY KEY,kind TEXT NOT NULL,migration TEXT NOT NULL,payload BLOB NOT NULL,previous_sha256 TEXT NOT NULL,sha256 TEXT NOT NULL)"
    )


