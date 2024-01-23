"""Coherent SQLite backup and content-addressed application-state evidence."""

from contextlib import closing
from pathlib import Path
import sqlite3

from .migration_model import PREFIX
from .migration_history import STACK, EVENTS
from .sqlite_inspect import Budget, database_snapshot, reader, verify_database_snapshot
from .sqlite_seed import canonical, identity, MAX_DATABASE, quoted, typed
from .redaction import secret_key
import copy

FORMAT = "reprolattice.migration-snapshot.v1"
ROWID = "_reprolattice_rowid"


def verify_migration_snapshot(value):
    if (
        not isinstance(value, dict)
        or value.get("format") != FORMAT
        or value.get("sha256")
        != identity({key: item for key, item in value.items() if key != "sha256"})
    ):
        raise ValueError("invalid migration snapshot format or identity")
    if set(value) != {"format", "schema", "tables", "sha256", "foreign_key_errors"}:
        raise ValueError("unsupported migration snapshot fields")
    errors = value["foreign_key_errors"]
    if (
        not isinstance(errors, list)
        or len(errors) > 21
        or any(not isinstance(row, list) or len(row) != 4 for row in errors)
    ):
        raise ValueError("invalid bounded foreign-key diagnostics")
    portable = copy.deepcopy(value)
    portable.pop("foreign_key_errors")
    portable["format"] = "reprolattice.sqlite-snapshot.v1"
    portable["sha256"] = identity(
        {key: item for key, item in portable.items() if key != "sha256"}
    )
    verify_database_snapshot(portable)
    for name, table in value["tables"].items():
        if secret_key(name) or any(
            secret_key(column["name"]) for column in table["columns"]
        ):
            raise ValueError(
                "migration evidence refuses named sensitive tables/columns"
            )
    return value


