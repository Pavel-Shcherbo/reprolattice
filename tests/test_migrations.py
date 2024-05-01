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

