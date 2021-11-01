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

    def test_seed_typed_nulls_and_keys(self):
        self.create()
        self.assertTrue(check_queries(self.path, checks())["passed"])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(
                db.execute("PRAGMA table_info(items)").fetchall()[0][2], "INTEGER"
            )
            self.assertEqual(db.execute("SELECT COUNT(*) FROM items").fetchone()[0], 2)
        self.assertEqual(
            verify_database_snapshot(database_snapshot(self.path))["tables"]["items"][
                "rows"
            ][0]["id"]["type"],
            "integer",
        )

    def test_binary_real_and_integer_results_are_distinct(self):
        definition = {
            "version": 1,
            "tables": [
                {
                    "name": "cells",
                    "columns": [
                        {"name": "i", "type": "INTEGER", "nullable": False},
                        {"name": "r", "type": "REAL", "nullable": False},
                        {"name": "b", "type": "BLOB", "nullable": False},
                    ],
                    "rows": [{"i": 1, "r": 1.0, "b": {"$blob": "00ff"}}],
                }
            ],
        }
        self.create(definition)
        rule = [
            {
                "id": "typed",
                "sql": "SELECT * FROM cells",
                "expected": [{"i": 1, "r": 1.0, "b": {"$blob": "00ff"}}],
            }
        ]
        self.assertTrue(check_queries(self.path, rule)["passed"])
        rule[0]["expected"][0]["r"] = 1
        self.assertFalse(check_queries(self.path, rule)["passed"])

