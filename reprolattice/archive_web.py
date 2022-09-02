"""Local archive controls over saved suite evidence; no arbitrary command execution."""

import sqlite3

from .reports import junit_xml
from .resources import state_directory
from .run_contract import fingerprint, sha, validate_run
from .run_registry import RunRegistry
from .suite_config import named

PROJECT = "inventory-workbench"
FIELDS = {
    "overview": {"after", "baseline_after"},
    "archive": {"report", "request_key", "label"},
    "inspect": {"record"},
    "baseline": {"name", "after"},
    "move": {"name", "record", "generation", "reason"},
    "compare": {"record", "before", "baseline", "generation"},
    "history": {"source", "after", "status"},
    "junit": {"record"},
}


def cursor(value, label="cursor"):
    if type(value) is not int or not 0 <= value <= 9223372036854775807:
        raise ValueError(label + " must be a bounded nonnegative integer")
    return value


