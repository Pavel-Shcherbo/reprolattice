"""Isolated migration outcomes, forensic failures and independent evidence replay."""

import copy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from reprolattice.migration_bundle import verify_migration_bundle, write_manifest
from reprolattice.migration_engine import MigrationDatabase
from reprolattice.migration_model import compile_migrations
from reprolattice.migration_runner import qualify_migrations
from reprolattice.migration_state import read_app_snapshot, SnapshotFiles, ROWID
from reprolattice.sqlite_seed import canonical, create_database

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def statement(sql, label="change", parameters=None):
    return {"id": label, "sql": sql, "parameters": parameters or []}


def simple_plan(up, down="SELECT 1"):
    checks = [{"id": "readable", "sql": "SELECT 1 AS ok", "expected": [{"ok": 1}]}]
    return {
        "version": 1,
        "name": "rehearsal",
        "baseline_checks": copy.deepcopy(checks),
        "migrations": [
            {
                "id": "first",
                "before_checks": copy.deepcopy(checks),
                "up": [statement(up)],
                "after_checks": copy.deepcopy(checks),
                "down": [statement(down)],
                "rollback_checks": copy.deepcopy(checks),
            }
        ],
    }


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan = json.loads((EXAMPLES / "inventory-migrations.json").read_text())
        self.seed = json.loads((EXAMPLES / "inventory-seed.json").read_text())
        self.out = self.root / "run"

    def run_plan(self, plan=None):
        return qualify_migrations(plan or self.plan, self.out, seed=self.seed)

    def source(self, sql):
        path = self.root / "source.sqlite"
        with closing(sqlite3.connect(path)) as db:
            db.executescript(sql)
        return path

    def assert_failed_clean(self, report, phase=0):
        result = report["phases"][phase]
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["rollback_verified"], result)
        self.assertEqual(result["before"], result["after"])
        self.assertFalse(report["qualification_passed"])
        return result

    def test_complete_cycle_repeat_history_and_readonly_replay(self):
        report = self.run_plan()
        self.assertTrue(report["qualification_passed"])
        self.assertEqual(
            [p["status"] for p in report["phases"]],
            ["applied", "already_applied"] * 2 + ["reverted", "already_absent"] * 2,
        )
        self.assertEqual(len(report["final_state"]["events"]), 4)
        before = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in self.out.iterdir()
            if p.is_file()
        }
        self.assertTrue(verify_migration_bundle(self.out)["qualification_passed"])
        after = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in self.out.iterdir()
            if p.is_file()
        }
        self.assertEqual(before, after)

    def test_sql_failure_retains_uncommitted_candidate_and_rolls_back(self):
        self.plan["migrations"][0]["up"].append(
            statement("INSERT INTO absent VALUES (1)", "bad")
        )
        result = self.assert_failed_clean(self.run_plan())
        self.assertNotEqual(result["candidate"], result["before"])
        self.assertEqual(result["failed_statement"], "bad")
        self.assertEqual(result["failure_stage"], "statements")
        self.assertTrue(result["candidate_in_transaction"])
        proof = verify_migration_bundle(self.out)
        self.assertTrue(proof["passed"])
        self.assertFalse(proof["qualification_passed"])

    def test_postcondition_failure_is_not_successful_migration(self):
        self.plan["migrations"][0]["after_checks"][1]["expected"][0]["total"] = 100
        result = self.assert_failed_clean(self.run_plan())
        self.assertEqual(result["failure_stage"], "postconditions")
        self.assertFalse(result["postconditions"]["passed"])
        self.assertNotEqual(result["candidate"], result["before"])

    def test_inexact_reverse_preserves_applied_state(self):
        plan = simple_plan("UPDATE inventory SET available=100", "SELECT 1")
        report = self.run_plan(plan)
        result = self.assert_failed_clean(report, 2)
        self.assertEqual(result["failure_stage"], "restoration")
        self.assertEqual(len(report["final_state"]["stack"]), 1)
        self.assertTrue(verify_migration_bundle(self.out)["passed"])

    def test_precondition_failure_performs_no_statement(self):
        self.plan["migrations"][0]["before_checks"][0]["expected"][0]["available"] = 0
        result = self.assert_failed_clean(self.run_plan())
        self.assertEqual(result["statements"], [])
        self.assertEqual(result["failure_stage"], "preconditions")

    def test_baseline_failure_is_retained_without_applying(self):
        self.plan["baseline_checks"][0]["expected"][0]["available"] = 0
        report = self.run_plan()
        self.assertEqual(report["phases"], [])
        self.assertFalse(report["qualification_passed"])
        self.assertTrue(verify_migration_bundle(self.out)["passed"])

    def test_denied_operations_are_rolled_back(self):
        for i, sql in enumerate(
            [
                "ATTACH DATABASE ':memory:' AS extra",
                "DETACH DATABASE main",
                "PRAGMA user_version=5",
                "BEGIN",
                "COMMIT",
                "SAVEPOINT x",
                "VACUUM",
                "SELECT load_extension('missing')",
                "CREATE TEMP TABLE scratch(n)",
                "CREATE VIRTUAL TABLE virtual USING fts5(text)",
                "DELETE FROM _reprolattice_migration_events",
                "DROP TABLE _reprolattice_migration_stack",
                "CREATE TABLE _reprolattice_intruder(n)",
            ]
        ):
            with self.subTest(sql=sql):
                self.out = self.root / str(i)
                result = self.assert_failed_clean(self.run_plan(simple_plan(sql)))
                self.assertEqual(result["failure_stage"], "statements")

    def test_multiple_statements_rejected(self):
        self.assert_failed_clean(
            self.run_plan(
                simple_plan("UPDATE inventory SET available=0; DELETE FROM receipts")
            )
        )

    def test_reserved_rename_cannot_escape_history_guard(self):
        result = self.assert_failed_clean(
            self.run_plan(
                simple_plan("ALTER TABLE inventory RENAME TO _reprolattice_intruder")
            )
        )
        self.assertIn("reserved", result["error"])

    def test_bound_text_is_literal_not_sql(self):
        plan = simple_plan(
            "INSERT INTO inventory VALUES (?,?)", "DELETE FROM inventory WHERE part=?"
        )
        payload = "x'); DROP TABLE inventory; --"
        plan["migrations"][0]["up"][0]["parameters"] = [payload, 4]
        plan["migrations"][0]["down"][0]["parameters"] = [payload]
        self.assertTrue(self.run_plan(plan)["qualification_passed"])

    def test_returning_overflow_rolls_back(self):
        sql = "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<1001) SELECT x FROM n"
        result = self.assert_failed_clean(self.run_plan(simple_plan(sql)))
        self.assertIn("1,000", result["error"])

    def test_recursive_vm_work_budget(self):
        sql = "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n) SELECT sum(x) FROM n"
        result = self.assert_failed_clean(self.run_plan(simple_plan(sql)))
        self.assertIn("migration", result["error"])

    def test_mid_step_cancellation_retains_rollback_but_not_full_replay(self):
        calls = 0

        def cancel():
            nonlocal calls
            calls += 1
            return calls > 20

        plan = simple_plan(
            "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<100000) SELECT sum(x) FROM n"
        )
        report = qualify_migrations(
            plan, self.out, seed=self.seed, should_cancel=cancel
        )
        phase = report["phases"][0]
        self.assertEqual(phase["status"], "cancelled")
        self.assertTrue(phase["rollback_verified"])
        self.assertFalse(verify_migration_bundle(self.out)["replay_complete"])

    def test_hidden_rowid_changes_are_not_exact_restoration(self):
        report = self.run_plan(simple_plan("UPDATE inventory SET rowid=7", "SELECT 1"))
        self.assert_failed_clean(report, 2)
        snapshot = json.loads(
            (self.out / "snapshots" / (report["source_snapshot"] + ".json")).read_text()
        )
        self.assertEqual(snapshot["tables"]["inventory"]["rows"][0][ROWID]["value"], 1)

    def test_autoincrement_sequence_is_part_of_restoration(self):
        source = self.source(
            "CREATE TABLE items(id INTEGER PRIMARY KEY AUTOINCREMENT); INSERT INTO items DEFAULT VALUES;"
        )
        plan = simple_plan(
            "INSERT INTO items DEFAULT VALUES", "DELETE FROM items WHERE id=2"
        )
        report = qualify_migrations(plan, self.out, source=source)
        self.assert_failed_clean(report, 2)
        baseline = read_app_snapshot(source)
        self.assertIn("sqlite_sequence", baseline["tables"])

    def test_without_rowid_table_and_alter_column(self):
        source = self.source(
            'CREATE TABLE items("id" TEXT PRIMARY KEY,"n" INTEGER) WITHOUT ROWID; INSERT INTO items VALUES(\'one\',2);'
        )
        plan = simple_plan(
            "ALTER TABLE items RENAME COLUMN n TO value",
            "ALTER TABLE items RENAME COLUMN value TO n",
        )
        report = qualify_migrations(plan, self.out, source=source)
        self.assertTrue(report["qualification_passed"], report["phases"])
        self.assertNotIn(ROWID, read_app_snapshot(source)["tables"]["items"]["rows"][0])

    def test_all_rowid_aliases_shadowed_refused(self):
        source = self.source(
            "CREATE TABLE items(rowid INTEGER,_rowid_ INTEGER,oid INTEGER)"
        )
        with self.assertRaisesRegex(ValueError, "shadowed"):
            qualify_migrations(simple_plan("SELECT 1"), self.out, source=source)

    def test_wal_source_captured_without_changing_committed_content(self):
        source = self.root / "wal.sqlite"
        with closing(sqlite3.connect(source, isolation_level=None)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE items(id INTEGER PRIMARY KEY, n INTEGER)")
            db.execute("INSERT INTO items VALUES(1,9)")
            before = read_app_snapshot(source)
            report = qualify_migrations(
                simple_plan("UPDATE items SET n=10", "UPDATE items SET n=9"),
                self.out,
                source=source,
            )
            self.assertTrue(report["qualification_passed"])
            self.assertEqual(before, read_app_snapshot(source))
            self.assertEqual(report["source_snapshot"], before["sha256"])

    def test_source_symlink_and_create_only_destination(self):
        source = self.root / "original.sqlite"
        create_database(self.seed, source)
        link = self.root / "link.sqlite"
        link.symlink_to(source)
        with self.assertRaises(ValueError):
            qualify_migrations(self.plan, self.out, source=link)
        self.out = self.root / "valid"
        self.run_plan()
        before = (self.out / "report.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_plan()
        self.assertEqual(before, (self.out / "report.json").read_bytes())

    def test_bad_plan_refused_before_output_directory(self):
        for change in [
            lambda p: p.update(version=True),
            lambda p: p.update(extra=1),
            lambda p: p["migrations"].append(copy.deepcopy(p["migrations"][0])),
            lambda p: p["migrations"][0]["up"][0].update(parameters=[True]),
        ]:
            plan = copy.deepcopy(self.plan)
            change(plan)
            with self.assertRaises(ValueError):
                self.run_plan(plan)
            self.assertFalse(self.out.exists())

    def test_rehashed_fabricated_outcome_fails_fresh_replay(self):
        self.run_plan()
        path = self.out / "report.json"
        report = json.loads(path.read_text())
        report["phases"][0]["statements"][1]["rowcount"] = 500
        path.write_bytes(canonical(report) + b"\n")
        (self.out / "manifest.json").unlink()
        write_manifest(self.out)
        with self.assertRaisesRegex(ValueError, "fresh migration SQL replay"):
            verify_migration_bundle(self.out)

