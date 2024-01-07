"""Rehearse ordered up/repeat/down cycles from an untouched copied baseline."""

from pathlib import Path
import platform
import sqlite3
import time
import uuid

from .migration_engine import MigrationDatabase
from .migration_model import compile_migrations, compact_checks
from .migration_state import SnapshotFiles, clone_database, read_app_snapshot
from .sqlite_inspect import check_queries
from .sqlite_seed import canonical, create_database

FORMAT = "reprolattice.migration-report.v1"


