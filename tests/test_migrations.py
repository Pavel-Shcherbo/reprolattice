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

