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


