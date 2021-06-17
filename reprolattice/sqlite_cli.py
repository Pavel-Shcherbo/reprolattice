"""Create fixtures, inspect SQLite state and compare portable logical snapshots."""

import argparse
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from .jsonutil import strict_json
from .sqlite_seed import canonical, create_database
from .sqlite_inspect import (
    check_queries,
    database_snapshot,
    compare_snapshots,
    verify_database_snapshot,
)


def load(path, limit):
    with Path(path).open("rb") as stream:
        return strict_json(stream.read(limit + 1), max_bytes=limit)


def save_snapshot(snapshot, path):
    verify_database_snapshot(snapshot)
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".sqlite-snapshot-", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(canonical(snapshot) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"path": str(path), "sha256": snapshot["sha256"]}


