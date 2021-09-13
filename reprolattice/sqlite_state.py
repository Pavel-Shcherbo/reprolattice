"""SQLite state setup and postconditions shared by suite execution and CLI."""

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .jsonutil import strict_json
from .sqlite_seed import canonical, compile_seed, create_database, identity
from .sqlite_inspect import check_queries, compare_snapshots, database_snapshot, reader


@dataclass(frozen=True)
class SQLiteState:
    path: str
    seed: dict
    queries: tuple
    sha256: str
    input_bytes: int


