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


