"""Bounded migration evidence inventories and fresh offline SQL replay."""

import hashlib
from pathlib import Path
import re
import tempfile

from .jsonutil import strict_json
from .migration_model import compile_migrations
from .migration_state import read_app_snapshot, verify_migration_snapshot
from .sqlite_seed import canonical, identity

MAX_BUNDLE = 80 * 1024 * 1024
FILES = {
    "plan.json": 4 * 1024 * 1024,
    "report.json": 8 * 1024 * 1024,
    "baseline.sqlite": 16 * 1024 * 1024,
    "working.sqlite": 16 * 1024 * 1024,
}


