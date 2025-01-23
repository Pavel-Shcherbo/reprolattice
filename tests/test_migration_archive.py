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

    def test_failure_candidate_and_postrollback_rows_are_distinct(self):
        record = self.run_control("statement_failure")["record"]["id"]
        value = inspect_rehearsal(self.archive, "project", record)
        self.assertFalse(value["report"]["qualification_passed"])
        candidate = phase_table(self.archive, "project", record, 0, "stock_totals")
        self.assertEqual(candidate["page"]["items"][0]["total"]["value"], 99)
        self.assertTrue(value["report"]["phases"][0]["rollback_verified"])
        with self.assertRaises(ValueError):
            phase_table(
                self.archive, "project", record, 0, "stock_totals", side="after"
            )
        diff = phase_table(
            self.archive, "project", record, 0, "stock_totals", view="diff"
        )
        self.assertEqual(diff["page"]["counts"]["added"], 1)

    def test_broken_reverse_preserves_applied_state(self):
        value = self.run_control("broken_rollback")
        report = value["report"]
        self.assertFalse(report["qualification_passed"])
        self.assertEqual(len(report["final_state"]["stack"]), 2)
        index = next(
            i for i, p in enumerate(report["phases"]) if p["status"] == "failed"
        )
        self.assertEqual(report["phases"][index]["failure_stage"], "restoration")
        page = phase_table(
            self.archive,
            "project",
            value["record"]["id"],
            index,
            "inventory",
            side="after",
        )
        self.assertEqual(page["page"]["items"][0]["available"]["value"], 100)

    def test_portable_envelope_verifies_after_archive_removal(self):
        value = self.run_control()
        document = export_rehearsal(self.archive, "project", value["record"]["id"])
        import shutil

        shutil.rmtree(self.archive.root)
        proof = verify_retained_migration(document)
        self.assertTrue(proof["passed"])
        self.assertTrue(proof["qualification_passed"])

    def test_failed_envelope_can_be_valid_evidence(self):
        value = self.run_control("statement_failure")
        proof = verify_retained_migration(
            export_rehearsal(self.archive, "project", value["record"]["id"])
        )
        self.assertTrue(proof["passed"])
        self.assertFalse(proof["qualification_passed"])

    def test_completed_manifest_and_file_tamper_cannot_be_hidden(self):
        value = self.run_control()
        record = value["record"]["id"]
        root = self.archive.bundle(record)
        (root / "report.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "file changed"):
            self.archive.get("project", record)

    def test_envelope_rejects_paths_encoding_and_receipt_tamper(self):
        value = self.run_control()
        document = export_rehearsal(self.archive, "project", value["record"]["id"])
        for mutate in [
            lambda d: d["files"].update({"../outside": "AA=="}),
            lambda d: d["files"].update({"plan.json": "!!!!"}),
            lambda d: d["record"].update(manifest_sha256="0" * 64),
        ]:
            forged = copy.deepcopy(document)
            mutate(forged)
            forged["sha256"] = identity(
                {k: v for k, v in forged.items() if k != "sha256"}
            )
            with self.assertRaises(ValueError):
                verify_retained_migration(forged)

