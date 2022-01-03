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

    def test_duplicate_unique_foreign_keys_and_nulls_rejected_before_creation(self):
        for transform in ["duplicate", "null", "wrongtype", "foreign"]:
            definition = seed()
            if transform == "duplicate":
                definition["tables"][0]["rows"].append({"id": 1, "value": "other"})
            elif transform == "null":
                definition["tables"][0]["rows"][0]["id"] = None
            elif transform == "wrongtype":
                definition["tables"][0]["rows"][0]["id"] = True
            else:
                definition["tables"][0]["foreign_keys"] = [
                    {
                        "columns": ["id"],
                        "table": "items",
                        "references": ["id"],
                        "on_delete": "SET NULL",
                    }
                ]
            with self.subTest(transform=transform), self.assertRaises(ValueError):
                create_database(definition, self.path)
            self.assertFalse(self.path.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_parent_after_child_seed_order_with_deferred_foreign_keys(self):
        definition = json.loads((EXAMPLES / "inventory-seed.json").read_text())
        definition["tables"][1]["rows"] = [{"id": 1, "part": "part-42", "quantity": 8}]
        definition["tables"].reverse()
        self.create(definition)
        self.assertTrue(database_snapshot(self.path)["tables"]["receipts"]["rows"])
        definition["tables"][0]["rows"][0]["part"] = "missing"
        with self.assertRaisesRegex(ValueError, "referenced"):
            compile_seed(definition)

    def test_no_overwrite_of_database_or_symlink(self):
        self.create()
        original = self.path.read_bytes()
        with self.assertRaises(FileExistsError):
            self.create()
        self.assertEqual(self.path.read_bytes(), original)
        link = self.root / "link.sqlite"
        link.symlink_to(self.path)
        with self.assertRaises(FileExistsError):
            create_database(seed(), link)
        self.assertFalse(list(self.root.glob(".sqlite-seed-*")))

    def test_queries_deny_writes_attachments_pragmas_and_unsafe_functions(self):
        self.create()
        before = database_snapshot(self.path)["sha256"]
        for sql in [
            "DELETE FROM items",
            "UPDATE items SET value='changed'",
            "DROP TABLE items",
            "ATTACH DATABASE 'other.sqlite' AS other",
            "PRAGMA writable_schema=ON",
            "SELECT load_extension('anything')",
            "SELECT randomblob(100)",
        ]:
            with self.subTest(sql=sql):
                report = check_queries(
                    self.path, [{"id": "denied", "sql": sql, "expected": []}]
                )
                self.assertFalse(report["passed"])
                self.assertIn("error", report["queries"][0])
        self.assertEqual(database_snapshot(self.path)["sha256"], before)
        self.assertFalse((self.root / "other.sqlite").exists())

    def test_parameters_aggregates_and_cte(self):
        self.create()
        report = check_queries(
            self.path,
            [
                {
                    "id": "aggregate",
                    "sql": "WITH selected AS (SELECT id FROM items WHERE id>?) SELECT count(*) AS n, sum(id) AS total FROM selected",
                    "parameters": [0],
                    "expected": [{"n": 2, "total": 3}],
                }
            ],
        )
        self.assertTrue(report["passed"])

    def test_order_and_duplicate_row_multiplicity(self):
        self.create()
        rule = {
            "id": "order",
            "sql": "SELECT id FROM items ORDER BY id DESC",
            "expected": [{"id": 1}, {"id": 2}],
        }
        self.assertFalse(check_queries(self.path, [rule])["passed"])
        rule["order"] = "unordered"
        self.assertTrue(check_queries(self.path, [rule])["passed"])
        rule["sql"] = "SELECT id FROM items UNION ALL SELECT id FROM items"
        self.assertFalse(check_queries(self.path, [rule])["passed"])

    def test_row_vm_and_cancellation_budgets(self):
        self.create()
        sql = "WITH RECURSIVE n(v) AS (VALUES(1) UNION ALL SELECT v+1 FROM n WHERE v<2000) SELECT v FROM n"
        result = check_queries(
            self.path, [{"id": "bounded", "sql": sql, "expected": []}]
        )
        self.assertFalse(result["passed"])
        self.assertIn("1,000", result["queries"][0]["error"])
        infinite = "WITH RECURSIVE n(v) AS (VALUES(1) UNION ALL SELECT v+1 FROM n) SELECT sum(v) FROM n"
        with self.assertRaisesRegex(ValueError, "budget"):
            check_queries(
                self.path, [{"id": "bounded", "sql": infinite, "expected": []}]
            )
        with self.assertRaisesRegex(ValueError, "cancelled"):
            database_snapshot(self.path, should_cancel=lambda: True)

    def test_logical_snapshot_ignores_row_insertion_order(self):
        definition = seed()
        definition["tables"][0]["primary_key"] = []
        self.create(definition)
        before = database_snapshot(self.path)
        definition["tables"][0]["rows"].reverse()
        other = self.root / "other.sqlite"
        create_database(definition, other)
        self.assertTrue(compare_snapshots(before, database_snapshot(other))["equal"])
        self.assertNotEqual(self.path.read_bytes(), other.read_bytes())

