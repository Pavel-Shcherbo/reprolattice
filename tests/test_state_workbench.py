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

    def save(self, document=None, key="healthy", label=""):
        return self.archive().record(
            PROJECT,
            copy.deepcopy(document or self.healthy),
            request_key=key,
            label=label,
        )

    def test_real_capture_records_all_three_successful_state_pairs(self):
        self.assertTrue(self.healthy["report"]["passed"])
        self.assertEqual(len(self.healthy["pairs"]), 3)
        for pair in self.healthy["pairs"]:
            self.assertEqual(
                pair["before"]["tables"]["inventory"]["rows"][0]["available"],
                {"type": "integer", "value": 99},
            )
            quantity = pair["after"]["tables"]["inventory"]["rows"][0]["available"][
                "value"
            ]
            self.assertIn(quantity, (0, 7, 12))
            self.assertEqual(
                pair["after"]["tables"]["receipts"]["rows"][0]["quantity"]["value"],
                quantity,
            )

    def test_omitted_write_fails_database_checks_even_when_http_passes(self):
        self.assertEqual(self.faulty["report"]["counts"]["failed"], 3)
        for case in self.faulty["report"]["cases"]:
            self.assertTrue(case["detail"]["passed"])
            self.assertFalse(case["sqlite"][0]["passed"])
        for pair in self.faulty["pairs"]:
            self.assertEqual(pair["before"], pair["after"])

    def test_inspection_exposes_checks_schema_and_typed_row_changes(self):
        record = self.save()
        view = self.api("inspect", record=record["id"])
        self.assertTrue(view["record"]["capture_complete"])
        pair = view["pairs"][1]
        self.assertTrue(pair["checks"]["passed"])
        self.assertEqual(
            {row["name"] for row in pair["tables"]}, {"inventory", "receipts"}
        )
        args = {
            "record": record["id"],
            "case": pair["case"],
            "path": pair["path"],
            "table": "inventory",
        }
        diff = self.api("diff", **args)
        self.assertEqual(diff["identity_mode"], "declared_primary_key")
        self.assertEqual(
            diff["counts"], {"added": 0, "removed": 0, "modified": 1, "unchanged": 0}
        )
        self.assertEqual(diff["items"][0]["before"]["available"]["value"], 99)
        self.assertEqual(
            self.api("table", **args, side="before")["items"][0]["available"]["value"],
            99,
        )

