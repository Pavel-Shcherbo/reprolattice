"""Coherent SQLite backup and content-addressed application-state evidence."""

from contextlib import closing
from pathlib import Path
import sqlite3

from .migration_model import PREFIX
from .migration_history import STACK, EVENTS
from .sqlite_inspect import Budget, database_snapshot, reader, verify_database_snapshot
from .sqlite_seed import canonical, identity, MAX_DATABASE, quoted, typed
from .redaction import secret_key
import copy

FORMAT = "reprolattice.migration-snapshot.v1"
ROWID = "_reprolattice_rowid"


