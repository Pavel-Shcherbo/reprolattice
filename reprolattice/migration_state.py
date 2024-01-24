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


def app_snapshot(db, budget, *, diagnostic=False):
    db.set_authorizer(None)
    value = database_snapshot(
        None, _view=(db, budget), allow_foreign_key_errors=diagnostic
    )
    value["schema"] = [
        item
        for item in value["schema"]
        if item["name"] not in (STACK, EVENTS) and item["table"] not in (STACK, EVENTS)
    ]
    value["tables"] = {
        name: table
        for name, table in value["tables"].items()
        if name not in (STACK, EVENTS)
    }
    for name, sql in db.execute(
        "SELECT name,sql FROM sqlite_schema WHERE type='table' AND (name='sqlite_sequence' OR name GLOB 'sqlite_stat[1-4]') ORDER BY name"
    ):
        columns = [
            dict(
                zip(
                    (
                        "cid",
                        "name",
                        "declared_type",
                        "not_null",
                        "default",
                        "primary_key",
                        "hidden",
                    ),
                    row,
                )
            )
            for row in db.execute("PRAGMA table_xinfo(" + quoted(name) + ")")
        ]
        names = [column["name"] for column in columns]
        rows = [
            {key: typed(item) for key, item in zip(names, row)}
            for row in db.execute(
                "SELECT " + ",".join(map(quoted, names)) + " FROM " + quoted(name)
            )
        ]
        rows.sort(key=canonical)
        value["schema"].append(
            {"type": "table", "name": name, "table": name, "sql": sql}
        )
        value["tables"][name] = {
            "columns": columns,
            "rows": rows,
            "sha256": identity(rows),
        }
    value["schema"].sort(key=lambda item: (item["type"], item["name"]))
    for name, table in value["tables"].items():
        budget.check()
        names = [column["name"] for column in table["columns"]]
        if ROWID in names:
            raise ValueError(
                "source column conflicts with the reserved hidden-row identity projection"
            )
        alias = next(
            (
                alias
                for alias in ("rowid", "_rowid_", "oid")
                if alias not in {column.casefold() for column in names}
            ),
            None,
        )
        if alias is None:
            raise ValueError(
                "all hidden rowid aliases are shadowed; this table cannot be qualified"
            )
        try:
            cursor = db.execute(
                "SELECT "
                + alias
                + ","
                + ",".join(map(quoted, names))
                + " FROM "
                + quoted(name)
            )
        except sqlite3.OperationalError as error:
            if "no such column" in str(error):
                continue
            raise
        rows = []
        for row in cursor:
            budget.check()
            rows.append(
                {
                    **{key: typed(item) for key, item in zip(names, row[1:])},
                    ROWID: typed(row[0]),
                }
            )
        table["columns"].append(
            {
                "cid": len(names),
                "name": ROWID,
                "declared_type": "INTEGER",
                "not_null": 1,
                "default": None,
                "primary_key": 0,
                "hidden": 1,
            }
        )
        rows.sort(key=canonical)
        table["rows"] = rows
        table["sha256"] = identity(rows)
    value["foreign_key_errors"] = [
        list(row) for row in db.execute("PRAGMA foreign_key_check").fetchmany(21)
    ]
    value["format"] = FORMAT
    value["sha256"] = identity(
        {key: item for key, item in value.items() if key != "sha256"}
    )
    verify_migration_snapshot(value)
    return value


def read_app_snapshot(path):
    with reader(path, timeout=2) as (db, budget):
        return app_snapshot(db, budget)


