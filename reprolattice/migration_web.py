"""Reviewed migration controls with scoped evidence; no browser SQL or file paths."""

import copy
import json
import sqlite3
import threading

from .migration_archive import MigrationArchive, run_id, label_text
from .migration_views import inspect_rehearsal, phase_table, export_rehearsal
from .migration_bundle import verify_migration_bundle
from .resources import examples_directory, state_directory
from .suite_config import named

PROJECT = "inventory-migration-workbench"
LOCK = threading.Lock()
PROFILES = ("round_trip", "statement_failure", "broken_rollback")
FIELDS = {
    "overview": {"after"},
    "run": {"profile", "request_key", "label"},
    "inspect": {"record"},
    "table": {"record", "phase", "table", "side", "view", "offset"},
    "export": {"record"},
    "replay": {"record"},
    "recover": {"record", "generation"},
}


def control_inputs(profile):
    if profile not in PROFILES:
        raise ValueError("unknown reviewed migration profile")
    root = examples_directory()
    plan = json.loads((root / "inventory-migrations.json").read_text())
    seed = json.loads((root / "inventory-seed.json").read_text())
    if profile == "statement_failure":
        plan["migrations"][0]["up"].append(
            {
                "id": "missing_table",
                "sql": "INSERT INTO deliberately_missing VALUES(1)",
                "parameters": [],
            }
        )
    elif profile == "broken_rollback":
        plan["migrations"][1]["down"] = [
            {"id": "incomplete_reverse", "sql": "SELECT 1", "parameters": []}
        ]
        plan["migrations"][1]["rollback_checks"] = copy.deepcopy(
            plan["migrations"][1]["after_checks"]
        )
    return plan, seed


def evaluate_migrations(params):
    action = params.get("action", "overview")
    if (
        not isinstance(action, str)
        or action not in FIELDS
        or set(params) - ({"mode", "action"} | FIELDS[action])
    ):
        raise ValueError("unknown migration action or unsupported fields")
    if "record" in FIELDS[action]:
        run_id(params.get("record"))
    root = state_directory("reprolattice") / "migration-workbench"
    if action == "overview" and not root.exists():
        if type(params.get("after", 0)) is not int or params.get("after", 0) < 0:
            raise ValueError("invalid migration list cursor")
        return {"items": [], "next_cursor": None}
    try:
        archive = MigrationArchive(root)
        if action == "overview":
            return archive.list(PROJECT, after=params.get("after", 0))
        if action == "run":
            named(params.get("request_key"), "migration request key")
            label_text(params.get("label", ""))
            plan, seed = control_inputs(params.get("profile", "round_trip"))
            if not LOCK.acquire(blocking=False):
                raise ValueError(
                    "a migration control is running; retry this request after it completes"
                )
            try:
                return archive.run(
                    PROJECT, plan, seed, params["request_key"], params.get("label", "")
                )
            finally:
                LOCK.release()
        if action == "inspect":
            return inspect_rehearsal(archive, PROJECT, params["record"])
        if action == "table":
            return phase_table(
                archive,
                PROJECT,
                params["record"],
                params.get("phase"),
                params.get("table"),
                side=params.get("side", "candidate"),
                view=params.get("view", "rows"),
                offset=params.get("offset", 0),
            )
        if action == "export":
            return export_rehearsal(archive, PROJECT, params["record"])
        if action == "recover":
            return archive.recover(PROJECT, params["record"], params.get("generation"))
        archive.get(PROJECT, params["record"])
        return verify_migration_bundle(archive.bundle(params["record"]))
    except sqlite3.Error as error:
        raise ValueError("local migration archive: " + str(error)) from error
