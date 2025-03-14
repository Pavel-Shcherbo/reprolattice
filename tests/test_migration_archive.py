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

    def test_expired_completion_can_be_adopted_without_rerun(self):
        row, token = self.archive.reserve("project", self.plan, self.seed, "one")
        qualify_migrations(self.plan, self.archive.bundle(row["id"]), seed=self.seed)
        self.now = 701
        with self.assertRaises(ValueError):
            self.archive.complete("project", row["id"], token)
        result = self.archive.recover("project", row["id"], 1)
        self.assertEqual(result["record"]["status"], "completed")
        self.assertEqual(len(result["report"]["final_state"]["events"]), 4)
        with self.assertRaises(ValueError):
            self.archive.complete("project", row["id"], token)

    def test_partial_preparation_is_retained_as_interrupted(self):
        row, token = self.archive.reserve("project", self.plan, self.seed, "one")
        root = self.archive.bundle(row["id"])
        root.mkdir()
        (root / "partial").write_text("retained")
        with self.assertRaises(ValueError):
            self.archive.recover("project", row["id"], 1)
        self.now = 701
        result = self.archive.recover("project", row["id"], 1)
        self.assertEqual(result["record"]["status"], "interrupted")
        self.assertEqual((root / "partial").read_text(), "retained")
        self.assertEqual(
            self.archive.run("project", self.plan, self.seed, "one")["record"][
                "status"
            ],
            "interrupted",
        )
        with self.assertRaises(ValueError):
            self.archive.recover("project", row["id"], 1)

    def test_commit_time_expiry_does_not_publish_completion(self):
        row, token = self.archive.reserve("project", self.plan, self.seed, "one")
        qualify_migrations(self.plan, self.archive.bundle(row["id"]), seed=self.seed)
        clock = iter([100.0, 701.0])
        self.archive.clock = lambda: next(clock)
        with self.assertRaisesRegex(ValueError, "before commit"):
            self.archive.complete("project", row["id"], token)
        self.assertEqual(
            self.archive.get("project", row["id"])["record"]["status"], "running"
        )

    def test_concurrent_identical_requests_share_one_record(self):
        def run(_):
            return MigrationArchive(self.archive.root).run(
                "project", self.plan, self.seed, "one"
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            values = list(pool.map(run, range(4)))
        self.assertEqual(len({v["record"]["id"] for v in values}), 1)
        self.assertEqual(len(self.archive.list("project")["items"]), 1)
        record = values[0]["record"]["id"]
        self.assertTrue(
            self.archive.get("project", record)["report"]["qualification_passed"]
        )

    def test_wrong_reserved_seed_cannot_be_completed(self):
        row, token = self.archive.reserve("project", self.plan, self.seed, "one")
        changed = copy.deepcopy(self.seed)
        changed["tables"][0]["rows"][0]["available"] = 100
        qualify_migrations(self.plan, self.archive.bundle(row["id"]), seed=changed)
        with self.assertRaisesRegex(ValueError, "reserved seed"):
            self.archive.complete("project", row["id"], token)

    def test_table_validation_and_paging(self):
        value = self.run_control()
        record = value["record"]["id"]
        for kwargs in [
            {"phase": True},
            {"phase": 999},
            {"side": "other"},
            {"offset": -1},
            {"view": "sql"},
        ]:
            params = {
                "phase": 0,
                "table": "inventory",
                "side": "candidate",
                "view": "rows",
                "offset": 0,
            }
            params.update(kwargs)
            with self.assertRaises(ValueError):
                phase_table(self.archive, "project", record, **params)

    def test_cli_run_export_verify_and_pending_recovery(self):
        plan = self.root / "plan.json"
        seed = self.root / "seed.json"
        plan.write_text(json.dumps(self.plan))
        seed.write_text(json.dumps(self.seed))
        args = [
            sys.executable,
            "-m",
            "reprolattice.migration_runs",
            "--archive",
            str(self.archive.root),
            "--project",
            "project",
        ]

        def cli(*tail, expected=0):
            result = subprocess.run(
                args + list(map(str, tail)), capture_output=True, text=True
            )
            self.assertEqual(result.returncode, expected, result.stderr)
            return json.loads(result.stdout)

        value = cli("run", plan, "--seed", seed, "--request-key", "cli")
        path = self.root / "export.json"
        cli("export", value["record"]["id"], "--output", path)
        self.assertTrue(cli("verify", path)["passed"])
        pending, _ = self.archive.reserve("project", self.plan, self.seed, "abandoned")
        result = cli("recover", pending["id"], "--generation", 1, expected=1)
        self.assertEqual(result["record"]["status"], "interrupted")

    def test_list_paging_and_invalid_bounds(self):
        first = self.run_control(key="first")
        second = self.run_control(key="second")
        page = self.archive.list("project", limit=1)
        self.assertEqual(page["items"][0]["id"], first["record"]["id"])
        self.assertEqual(
            self.archive.list("project", after=page["next_cursor"])["items"][0]["id"],
            second["record"]["id"],
        )
        with self.assertRaises(ValueError):
            self.archive.list("project", after=True)

    def test_rehashed_manifest_cannot_replace_committed_receipt(self):
        value = self.run_control()
        root = self.archive.bundle(value["record"]["id"])
        with (root / "manifest.json").open("ab") as stream:
            stream.write(b" ")
        with self.assertRaisesRegex(ValueError, "committed receipt"):
            self.archive.get("project", value["record"]["id"])

