"""Retained rehearsal replay, scoped inspection, fenced recovery and UI controls."""

import copy
import concurrent.futures
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

from reprolattice.migration_archive import MigrationArchive
from reprolattice.migration_runner import qualify_migrations
from reprolattice.migration_views import (
    inspect_rehearsal,
    phase_table,
    export_rehearsal,
    verify_retained_migration,
)
from reprolattice.migration_web import control_inputs, evaluate_migrations
from reprolattice.sqlite_seed import identity


class MigrationArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 100.0
        self.archive = MigrationArchive(self.root / "archive", clock=lambda: self.now)
        self.plan, self.seed = control_inputs("round_trip")

    def run_control(self, profile="round_trip", key="one"):
        plan, seed = control_inputs(profile)
        return self.archive.run("project", plan, seed, key, "Control")

    def test_retry_restart_and_scoped_history(self):
        first = self.run_control()
        self.archive = MigrationArchive(self.root / "archive")
        self.assertEqual(first, self.run_control())
        self.assertEqual(len(self.archive.list("project")["items"]), 1)
        self.assertEqual(self.archive.list("other")["items"], [])
        with self.assertRaises(ValueError):
            self.archive.get("other", first["record"]["id"])
        with self.assertRaises(ValueError):
            self.run_control("statement_failure")

