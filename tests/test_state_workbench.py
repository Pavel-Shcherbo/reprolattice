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

    def test_archive_reopen_pagination_and_project_isolation(self):
        first = self.save()
        second = self.save(self.faulty, key="faulty")
        reopened = StateArchive(self.path)
        page = reopened.list(PROJECT, limit=1)
        self.assertEqual(page["items"][0]["id"], second["id"])
        self.assertEqual(
            reopened.list(PROJECT, after=page["next_cursor"])["items"][0]["id"],
            first["id"],
        )
        with self.assertRaisesRegex(ValueError, "unknown"):
            reopened.get("other", first["id"])
        self.assertEqual(reopened.list("other")["items"], [])

    def test_record_idempotency_conflicts_and_concurrent_writers(self):
        archive = self.archive()

        def save(_):
            return archive.record(PROJECT, self.healthy, request_key="same")["id"]

        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(len(set(pool.map(save, range(8)))), 1)
        self.assertEqual(len(archive.list(PROJECT)["items"]), 1)
        with self.assertRaisesRegex(ValueError, "conflict"):
            archive.record(PROJECT, self.faulty, request_key="same")
        with self.assertRaisesRegex(ValueError, "label"):
            archive.record(PROJECT, self.healthy, request_key="same", label="changed")

    def test_control_retry_returns_old_report_without_execution(self):
        archive = self.archive()
        original = execute_retained(
            plan(), archive, PROJECT, request_key="retry", label="control"
        )
        with patch(
            "reprolattice.state_service.run_suite",
            side_effect=AssertionError("reexecuted"),
        ):
            again = execute_retained(
                plan(), archive, PROJECT, request_key="retry", label="control"
            )
        self.assertEqual(original, again)
        with self.assertRaisesRegex(ValueError, "different controls"):
            execute_retained(
                plan(True), archive, PROJECT, request_key="retry", label="control"
            )

    def test_rehashed_snapshot_or_definition_changes_cannot_match_report(self):
        for mutate in (
            lambda d: d["pairs"][0]["after"]["tables"]["inventory"]["rows"][0][
                "available"
            ].update(value=100),
            lambda d: d["pairs"][0].update(definition_sha256="0" * 64),
            lambda d: d["pairs"].append(d["pairs"][0]),
            lambda d: d["pairs"][0].update(case="missing"),
        ):
            value = copy.deepcopy(self.healthy)
            mutate(value)
            rehash(value)
            with self.assertRaises(ValueError):
                validate_evidence(value)

    def test_forged_index_or_blob_is_detected_by_read_and_audit(self):
        record = self.save()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE state_runs SET summary=?", (b"{}",))
        with self.assertRaises(ValueError):
            self.api("inspect", record=record["id"])
        result = self.api("audit")
        self.assertFalse(result["passed"])
        self.assertFalse(result["items"][0]["passed"])

    def test_audit_pages_do_not_claim_whole_archive_pass(self):
        self.save()
        self.save(self.faulty, key="faulty")
        first = self.archive().audit(PROJECT, limit=1)
        self.assertTrue(first["page_passed"])
        self.assertFalse(first["complete"])
        self.assertFalse(first["passed"])
        final = self.archive().audit(PROJECT, after=first["next_cursor"], limit=1)
        self.assertTrue(final["complete"])
        self.assertTrue(final["page_passed"])
        self.assertFalse(final["passed"])
        self.assertTrue(self.archive().audit(PROJECT)["passed"])

    def test_invalid_browser_requests_do_not_create_archive(self):
        self.assertFalse(self.api("overview")["initialized"])
        for fields in (
            {"action": "run", "request_key": "valid", "omit_write": 1},
            {"action": "run", "request_key": "valid", "command": ["anything"]},
            {"action": "inspect", "record": "../outside"},
            {"action": "overview", "after": True},
            {
                "action": "table",
                "record": "a" * 64,
                "case": "x",
                "path": "../outside",
                "table": "inventory",
            },
            {
                "action": "table",
                "record": "a" * 64,
                "case": "x",
                "path": "state.sqlite",
                "table": "inventory",
                "side": [],
            },
            {
                "action": "diff",
                "record": "a" * 64,
                "case": "x",
                "path": "state.sqlite",
                "table": "inventory",
                "status": [],
            },
            {"action": "run", "request_key": "valid", "label": "\n"},
        ):
            with self.assertRaises(ValueError):
                evaluate({"mode": "state", **fields})
        self.assertFalse(self.path.exists())

    def test_unknown_record_pair_and_table_are_rejected(self):
        record = self.save()
        pair = self.healthy["pairs"][0]
        for kwargs in (
            {
                "record": "0" * 64,
                "case": pair["case"],
                "path": pair["path"],
                "table": "inventory",
            },
            {
                "record": record["id"],
                "case": "other",
                "path": pair["path"],
                "table": "inventory",
            },
            {
                "record": record["id"],
                "case": pair["case"],
                "path": pair["path"],
                "table": "missing",
            },
        ):
            with self.assertRaises(ValueError):
                self.api("diff", **kwargs)

    def test_concurrent_browser_run_refused_before_execution(self):
        RUN_LOCK.acquire()
        try:
            with self.assertRaisesRegex(ValueError, "already running"):
                self.api("run", request_key="locked")
        finally:
            RUN_LOCK.release()
        self.assertEqual(self.archive().list(PROJECT)["items"], [])

    def test_secret_parameters_and_sensitive_columns_refuse_retention(self):
        compiled = plan()
        case = replace(compiled.cases[0], secrets=("canary-secret",))
        with self.assertRaisesRegex(ValueError, "secret-parameter"):
            StateCollector(replace(compiled, cases=(case,)))
        seed = copy.deepcopy(compiled.cases[0].states[0].seed)
        seed["tables"][0]["columns"][0]["name"] = "password"
        state = replace(compiled.cases[0].states[0], seed=seed)
        case = replace(compiled.cases[0], states=(state,))
        with self.assertRaisesRegex(ValueError, "sensitive"):
            StateCollector(replace(compiled, cases=(case,)))

    def test_capture_budget_failure_is_explicit_incomplete_evidence(self):
        with patch("reprolattice.state_evidence.MAX_PAIR", 1):
            result = execute_retained(
                plan(), self.archive(), PROJECT, request_key="limited"
            )
        self.assertFalse(result["record"]["capture_complete"])
        self.assertEqual(result["record"]["retained_pairs"], 0)
        self.assertEqual(result["report"]["counts"]["failed"], 3)
        self.assertIn(
            "retention limit", result["report"]["cases"][0]["sqlite"][0]["error"]
        )

    def test_cancelled_cases_do_not_become_complete_capture(self):
        from reprolattice.suite_runner import run_suite

        collector = StateCollector(plan())
        report = run_suite(plan(), should_cancel=lambda: True, on_state=collector)
        record = self.archive().record(
            PROJECT, collector.finish(report), request_key="cancel"
        )
        self.assertFalse(record["capture_complete"])
        self.assertEqual(record["expected_pairs"], 3)

    def test_typed_blob_null_real_and_multiset_duplicates_preserved(self):
        # A real untyped table retains integer/real distinctions and duplicates.
        path = self.root / "mixed.sqlite"
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE mixed(value)")
            db.executemany(
                "INSERT INTO mixed VALUES(?)", [(1,), (1,), (None,), (b"\0",)]
            )
        before = database_snapshot(path)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("DELETE FROM mixed WHERE rowid=1")
            db.execute("INSERT INTO mixed VALUES(1.0)")
        after = database_snapshot(path)
        result = compare_rows(before, after, "mixed", status="all")
        self.assertEqual(result["identity_mode"], "row_multiset")
        self.assertEqual(
            result["counts"], {"added": 1, "removed": 1, "modified": 0, "unchanged": 3}
        )
        self.assertEqual(
            next(
                row["after"]["value"]["type"]
                for row in result["items"]
                if row["change"] == "added"
            ),
            "real",
        )
        self.assertEqual(sum(row["count"] for row in result["items"]), 5)

    def test_composite_keys_and_null_duplicate_keys_use_safe_fallback(self):
        path = self.root / "key.sqlite"
        with closing(sqlite3.connect(path)) as db, db:
            db.execute(
                "CREATE TABLE keyed(a TEXT,b INTEGER,v INTEGER,PRIMARY KEY(a,b))"
            )
            db.executemany(
                "INSERT INTO keyed VALUES(?,?,?)", [("x", 1, 2), ("x", 2, 3)]
            )
        before = database_snapshot(path)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("UPDATE keyed SET v=9 WHERE b=2")
        after = database_snapshot(path)
        result = compare_rows(before, after, "keyed")
        self.assertEqual(result["primary_key"], ["a", "b"])
        self.assertEqual(result["counts"]["modified"], 1)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("INSERT INTO keyed VALUES(NULL,1,2)")
        nullable = database_snapshot(path)
        self.assertEqual(
            compare_rows(before, nullable, "keyed")["identity_mode"], "row_multiset"
        )

    def test_schema_only_added_removed_tables_and_empty_diffs(self):
        pair = self.healthy["pairs"][0]
        before = pair["before"]
        self.assertEqual(compare_rows(before, before, "receipts")["items"], [])
        path = self.root / "schema.sqlite"
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE fresh(id INTEGER)")
        fresh = database_snapshot(path)
        self.assertTrue(compare_rows(before, fresh, "fresh")["schema_changed"])
        removed = compare_rows(before, fresh, "inventory")
        self.assertEqual(removed["counts"]["removed"], 1)

    def test_table_and_diff_pagination_complete_without_repeating_rows(self):
        path = self.root / "many.sqlite"
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE many(id INTEGER PRIMARY KEY,v TEXT)")
            db.executemany(
                "INSERT INTO many VALUES(?,?)", [(i, str(i)) for i in range(57)]
            )
        before = database_snapshot(path)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("UPDATE many SET v='new'")
        after = database_snapshot(path)
        for function in (
            lambda offset: table_page(after, "many", offset=offset, limit=7),
            lambda offset: compare_rows(before, after, "many", offset=offset, limit=7),
        ):
            items = []
            offset = 0
            while True:
                page = function(offset)
                items.extend(page["items"])
                if page["next_offset"] is None:
                    break
                offset = page["next_offset"]
            self.assertEqual(len(items), 57)
        for offset in (True, -1, 40001, 58):
            with self.assertRaises(ValueError):
                table_page(after, "many", offset=offset)

    def test_store_quota_and_unknown_schema_do_not_accept_partial_records(self):
        archive = self.archive()
        with patch("reprolattice.state_archive.MAX_STORE", 1):
            with self.assertRaisesRegex(ValueError, "256 MiB"):
                archive.record(PROJECT, self.healthy, request_key="quota")
        self.assertEqual(archive.list(PROJECT)["items"], [])
        other = self.root / "other.sqlite"
        with closing(sqlite3.connect(other)) as db, db:
            db.execute("CREATE TABLE unrelated(x)")
        with self.assertRaisesRegex(ValueError, "unrelated"):
            StateArchive(other, create=True)
        link = self.root / "link.sqlite"
        link.symlink_to(self.path)
        with self.assertRaises(ValueError):
            StateArchive(link)

    def test_rehashed_invalid_column_metadata_and_duplicate_schema_rejected(self):
        from reprolattice.sqlite_inspect import verify_database_snapshot

        for mutate in (
            lambda d: d["tables"]["inventory"]["columns"][0].update(primary_key=True),
            lambda d: d["tables"]["inventory"]["columns"][0].update(cid=4),
            lambda d: d["schema"].append(d["schema"][0]),
        ):
            value = copy.deepcopy(self.healthy["pairs"][0]["before"])
            mutate(value)
            rehash(value)
            with self.assertRaises(ValueError):
                verify_database_snapshot(value)

