"""Reviewed synthetic SQLite controls; never execute browser-supplied programs or paths."""

import json
import sqlite3
import threading

from .resources import examples_directory, state_directory
from .run_contract import sha
from .state_archive import StateArchive, cursor
from .state_diff import page_limits
from .state_service import execute_retained, inspect_record, inspect_table, inspect_diff
from .suite_config import compile_suite, named, relative_path

PROJECT = "inventory-state-workbench"
RUN_LOCK = threading.Lock()
FIELDS = {
    "overview": {"after"},
    "run": {"omit_write", "jobs", "request_key", "label"},
    "inspect": {"record"},
    "table": {"record", "case", "path", "table", "side", "offset"},
    "diff": {"record", "case", "path", "table", "status", "offset"},
    "export": {"record"},
    "audit": {"after"},
}


def evaluate_state(params):
    action = params.get("action", "overview") if isinstance(params, dict) else None
    if (
        not isinstance(action, str)
        or action not in FIELDS
        or set(params) - ({"mode", "action"} | FIELDS[action])
    ):
        raise ValueError("unknown state action or unsupported fields")
    if "record" in FIELDS[action]:
        sha(params.get("record"))
    if "after" in params:
        cursor(params["after"])
    if action in ("table", "diff"):
        if (
            not isinstance(params.get("case"), str)
            or not 1 <= len(params["case"]) <= 128
        ):
            raise ValueError("state case requires bounded text")
        relative_path(params.get("path"))
        if (
            not isinstance(params.get("table"), str)
            or not 1 <= len(params["table"]) <= 256
        ):
            raise ValueError("state table requires bounded text")
        page_limits(params.get("offset", 0), 25)
    if action == "table" and params.get("side", "after") not in ("before", "after"):
        raise ValueError("state table side must be before or after")
    if action == "diff" and params.get("status", "changed") not in (
        "changed",
        "all",
        "added",
        "removed",
        "modified",
        "unchanged",
    ):
        raise ValueError("unknown row change filter")
    if action == "run":
        named(params.get("request_key"), "state request key")
        if (
            type(params.get("omit_write", False)) is not bool
            or type(params.get("jobs", 2)) is not int
            or params.get("jobs", 2) not in (1, 2, 4)
        ):
            raise ValueError(
                "state controls require boolean omit_write and jobs 1, 2 or 4"
            )
        label = params.get("label", "")
        if (
            not isinstance(label, str)
            or len(label) > 128
            or any(ord(char) < 32 for char in label)
        ):
            raise ValueError("state label must be at most 128 printable characters")
    database = state_directory("reprolattice") / "state-workbench" / "states.sqlite"
    if action == "overview" and not database.exists():
        return {"initialized": False, "items": [], "next_cursor": None}
    try:
        archive = StateArchive(database, create=action == "run")
        if action == "run":
            if not RUN_LOCK.acquire(blocking=False):
                raise ValueError(
                    "a retained-state control is already running; wait for its result"
                )
            try:
                directory = examples_directory()
                definition = json.loads(
                    (directory / "inventory-state-suite.json").read_text()
                )
                if params.get("omit_write", False):
                    definition["command"].append("--omit-write")
                plan = compile_suite(definition, directory)
                return execute_retained(
                    plan,
                    archive,
                    PROJECT,
                    request_key=params["request_key"],
                    label=label,
                    jobs=params.get("jobs", 2),
                )
            finally:
                RUN_LOCK.release()
        if action == "overview":
            return {
                "initialized": True,
                **archive.list(PROJECT, after=params.get("after", 0)),
            }
        if action == "inspect":
            return inspect_record(archive, PROJECT, params["record"])
        if action in ("table", "diff"):
            args = (
                archive,
                PROJECT,
                params["record"],
                params["case"],
                params["path"],
                params["table"],
            )
            if action == "table":
                return inspect_table(
                    *args,
                    side=params.get("side", "after"),
                    offset=params.get("offset", 0),
                )
            return inspect_diff(
                *args,
                status=params.get("status", "changed"),
                offset=params.get("offset", 0),
            )
        if action == "audit":
            return archive.audit(PROJECT, after=params.get("after", 0))
        return archive.get(PROJECT, params["record"])
    except sqlite3.Error as error:
        raise ValueError("local state archive: " + str(error)) from error
