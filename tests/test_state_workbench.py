"""Actual state capture, durable archive, key-aware diff and refusal controls."""

import copy
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from reprolattice.jsonutil import strict_json
from reprolattice.resources import examples_directory
from reprolattice.sqlite_seed import identity, create_database
from reprolattice.sqlite_inspect import database_snapshot
from reprolattice.state_archive import StateArchive
from reprolattice.state_diff import compare_rows, table_page
from reprolattice.state_evidence import StateCollector, validate_evidence
from reprolattice.state_service import execute_retained, inspect_record
from reprolattice.state_web import PROJECT, RUN_LOCK
from reprolattice.suite_config import compile_suite
from reprolattice.web import evaluate


def plan(faulty=False):
    root = examples_directory()
    definition = json.loads((root / "inventory-state-suite.json").read_text())
    if faulty:
        definition["command"].append("--omit-write")
    return compile_suite(definition, root)


def rehash(snapshot):
    snapshot["sha256"] = identity(
        {key: value for key, value in snapshot.items() if key != "sha256"}
    )


class StateWorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as root:
            archive = StateArchive(Path(root) / "archive.sqlite", create=True)
            healthy = execute_retained(plan(), archive, PROJECT, request_key="healthy")
            faulty = execute_retained(
                plan(True), archive, PROJECT, request_key="faulty"
            )
            cls.healthy = archive.get(PROJECT, healthy["record"]["id"])["document"]
            cls.faulty = archive.get(PROJECT, faulty["record"]["id"])["document"]

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.patch = patch(
            "reprolattice.state_web.state_directory", return_value=self.root
        )
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.path = self.root / "state-workbench/states.sqlite"

    def archive(self):
        return StateArchive(self.path, create=True)

    def api(self, action, **values):
        return evaluate({"mode": "state", "action": action, **values})

