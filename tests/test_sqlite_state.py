"""State controls independent of HTTP success and physical database layout."""

import copy
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from reprolattice.sqlite_seed import compile_seed, create_database, identity
from reprolattice.sqlite_inspect import (
    check_queries,
    compare_snapshots,
    database_snapshot,
    verify_database_snapshot,
)
from reprolattice.sqlite_state import compile_states, prepare_states, inspect_states
from reprolattice.sqlite_cli import save_snapshot
from reprolattice.suite_config import compile_suite
from reprolattice.suite_runner import run_suite
from reprolattice.reports import failure_summary, write_reports

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def seed():
    return {
        "version": 1,
        "tables": [
            {
                "name": "items",
                "columns": [
                    {"name": "id", "type": "INTEGER", "nullable": False},
                    {"name": "value", "type": "TEXT", "nullable": True},
                ],
                "primary_key": ["id"],
                "rows": [{"id": 1, "value": "one"}, {"id": 2, "value": None}],
            }
        ],
    }


def checks():
    return [
        {
            "id": "rows",
            "sql": "SELECT id, value FROM items ORDER BY id",
            "expected": [{"id": 1, "value": "one"}, {"id": 2, "value": None}],
        }
    ]


class SQLiteStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "data.sqlite"

    def create(self, definition=None):
        return create_database(seed() if definition is None else definition, self.path)

