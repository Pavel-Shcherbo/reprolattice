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
    reader,
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

    def test_shared_read_view_restores_internal_access_without_leaking_sql_policy(self):
        self.create()
        with reader(self.path) as view:
            db, _ = view
            self.assertTrue(check_queries(self.path, checks(), _view=view)["passed"])
            snapshot = database_snapshot(self.path, _view=view)
            self.assertEqual(len(snapshot["tables"]["items"]["rows"]), 2)
            for sql in (
                "PRAGMA writable_schema=ON",
                "SELECT id FROM items; DELETE FROM items",
            ):
                rejected = [{"id": "unsafe", "sql": sql, "expected": []}]
                self.assertFalse(
                    check_queries(self.path, rejected, _view=view)["passed"]
                )
            self.assertEqual(database_snapshot(self.path, _view=view), snapshot)
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("INSERT INTO items VALUES(3, 'forbidden')")
            self.assertTrue(check_queries(self.path, checks(), _view=view)["passed"])

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

    def test_diff_reports_rows_and_schema_without_retaining_values(self):
        self.create()
        before = database_snapshot(self.path)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE items SET value='changed' WHERE id=1")
            db.execute("ALTER TABLE items ADD COLUMN extra TEXT")
        diff = compare_snapshots(before, database_snapshot(self.path))
        self.assertFalse(diff["equal"])
        self.assertTrue(diff["schema_changed"])
        self.assertEqual(diff["tables"][0]["rows_added"], 2)
        self.assertNotIn(
            "changed",
            json.dumps(diff)
            .replace("schema_changed", "")
            .replace('"kind": "changed"', ""),
        )

    def test_tampered_snapshot_or_storage_type_is_rejected(self):
        self.create()
        snapshot = database_snapshot(self.path)
        snapshot["tables"]["items"]["rows"][0]["id"]["value"] = 123
        with self.assertRaisesRegex(ValueError, "identity"):
            verify_database_snapshot(snapshot)
        snapshot = database_snapshot(self.path)
        snapshot["tables"]["items"]["rows"][0]["id"]["type"] = "text"
        table = snapshot["tables"]["items"]
        table["sha256"] = identity(table["rows"])
        snapshot["sha256"] = identity(
            {k: v for k, v in snapshot.items() if k != "sha256"}
        )
        with self.assertRaisesRegex(ValueError, "storage"):
            verify_database_snapshot(snapshot)

    def test_invalid_file_sidecar_symlink_and_corrupt_fk(self):
        self.path.write_bytes(b"not a database")
        with self.assertRaises((ValueError, sqlite3.Error)):
            database_snapshot(self.path)
        self.path.unlink()
        self.create()
        sidecar = Path(str(self.path) + "-wal")
        sidecar.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError, "symlink"):
            database_snapshot(self.path)
        sidecar.unlink()
        foreign = self.root / "foreign.sqlite"
        definition = json.loads((EXAMPLES / "inventory-seed.json").read_text())
        create_database(definition, foreign)
        with closing(sqlite3.connect(foreign)) as db, db:
            db.execute("INSERT INTO receipts VALUES(1,'missing',1)")
        with self.assertRaisesRegex(ValueError, "foreign"):
            database_snapshot(foreign)

    def test_state_setup_and_failed_postcondition(self):
        states = compile_states(
            [{"path": "nested/app.sqlite", "seed": seed(), "checks": checks()}]
        )
        workspace = self.root / "work"
        workspace.mkdir()
        prepared = prepare_states(workspace, states)
        self.assertTrue(inspect_states(workspace, prepared)[0]["passed"])
        with closing(sqlite3.connect(workspace / "nested/app.sqlite")) as db, db:
            db.execute("DELETE FROM items")
        result = inspect_states(workspace, prepared)[0]
        self.assertFalse(result["passed"])
        self.assertEqual(result["changes"]["tables"][0]["rows_removed"], 2)

    def test_seed_pins_path_overlap_and_full_preflight(self):
        definition = json.loads((EXAMPLES / "inventory-state-suite.json").read_text())
        definition["cases"][0]["sqlite"][0]["seed_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "pinned"):
            compile_suite(definition, EXAMPLES)
        definition = json.loads((EXAMPLES / "inventory-state-suite.json").read_text())
        definition["cases"][0]["sqlite"][0]["path"] = "inventory_state_client.py"
        with self.assertRaisesRegex(ValueError, "overlap"):
            compile_suite(definition, EXAMPLES)

    def test_healthy_and_omitted_write_are_distinguished_after_same_http_output(self):
        definition = json.loads((EXAMPLES / "inventory-state-suite.json").read_text())
        plan = compile_suite(definition, EXAMPLES)
        healthy = run_suite(plan, jobs=2)
        self.assertTrue(healthy["passed"])
        self.assertEqual(healthy["counts"]["passed"], 3)
        definition["command"].append("--omit-write")
        bad = run_suite(compile_suite(definition, EXAMPLES), jobs=2)
        self.assertFalse(bad["passed"])
        self.assertEqual(bad["counts"]["failed"], 3)
        for case in bad["cases"]:
            self.assertTrue(case["detail"]["passed"])
            self.assertFalse(case["sqlite"][0]["passed"])
            self.assertIn("SQLite", failure_summary(case))
        reports = self.root / "reports"
        write_reports(bad, reports)
        self.assertIn("SQLite inventory.sqlite", (reports / "junit.xml").read_text())

    def test_cli_and_atomic_snapshot_no_overwrite(self):
        definition = self.root / "seed.json"
        definition.write_text(json.dumps(seed()))
        snap = self.root / "snapshot.json"

        def cli(*args, expected=0):
            result = subprocess.run(
                [sys.executable, "-m", "reprolattice.sqlite_cli", *map(str, args)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, expected, result.stderr)
            return json.loads(result.stdout) if result.stdout else None

        cli("seed", definition, self.path)
        cli("snapshot", self.path, "--output", snap)
        self.assertTrue(cli("verify-snapshot", snap)["passed"])
        self.assertTrue(cli("compare", snap, snap)["equal"])
        cli("snapshot", self.path, "--output", snap, expected=2)
        second = self.root / "changed.json"
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DELETE FROM items")
        cli("snapshot", self.path, "--output", second)
        self.assertFalse(cli("compare", snap, second, expected=1)["equal"])
        self.assertFalse(list(self.root.glob(".sqlite-snapshot-*")))

    def test_generated_results_stop_at_cell_and_byte_limits(self):
        self.create()
        report = check_queries(
            self.path,
            [{"id": "blob", "sql": "SELECT zeroblob(65537) AS value", "expected": []}],
        )
        self.assertFalse(report["passed"])
        self.assertIn("64 KiB", report["queries"][0]["error"])
        sql = "WITH RECURSIVE n(v) AS (VALUES(1) UNION ALL SELECT v+1 FROM n WHERE v<900) SELECT hex(zeroblob(1000)) AS value FROM n"
        report = check_queries(self.path, [{"id": "bytes", "sql": sql, "expected": []}])
        self.assertFalse(report["passed"])
        self.assertIn("1 MiB", report["queries"][0]["error"])

    def test_malformed_field_types_are_input_errors(self):
        definition = json.loads((EXAMPLES / "inventory-seed.json").read_text())
        definition["tables"][1]["foreign_keys"][0]["on_delete"] = []
        with self.assertRaises(ValueError):
            compile_seed(definition)
        self.create()
        rule = checks()[0]
        rule["order"] = []
        with self.assertRaises(ValueError):
            check_queries(self.path, [rule])
        snapshot = database_snapshot(self.path)
        snapshot["schema"][0]["type"] = []
        snapshot["sha256"] = identity(
            {k: v for k, v in snapshot.items() if k != "sha256"}
        )
        with self.assertRaises(ValueError):
            verify_database_snapshot(snapshot)


if __name__ == "__main__":
    unittest.main()
