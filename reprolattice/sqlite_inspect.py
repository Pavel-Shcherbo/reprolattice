"""Bounded read-only SQLite checks and typed logical database snapshots."""

import copy
import math
import sqlite3
import time
from collections import Counter
from contextlib import contextmanager, closing, nullcontext
from pathlib import Path

from .jsonutil import validate_json
from .sqlite_seed import MAX_DATABASE, canonical, identity, quoted, sqlite_value, typed

FUNCTIONS = frozenset(
    "abs avg char coalesce count cume_dist dense_rank first_value format hex ifnull iif instr json_array json_array_length json_extract json_group_array json_group_object json_object json_type json_valid lag last_value lead length likelihood likely lower ltrim max min nth_value ntile nullif percent_rank printf quote rank replace round row_number rtrim sign substr substring sum total trim typeof unicode unlikely upper zeroblob".split()
)


class Budget:
    def __init__(self, timeout=2, should_cancel=None):
        if (
            type(timeout) not in (int, float)
            or not math.isfinite(timeout)
            or not 0 < timeout <= 10
        ):
            raise ValueError(
                "SQLite inspection timeout must be between 0 and 10 seconds"
            )
        if should_cancel is not None and not callable(should_cancel):
            raise ValueError("cancellation must be callable")
        self.deadline = time.monotonic() + timeout
        self.steps = 0
        self.cancelled = should_cancel
        self.reason = None

    def progress(self):
        self.steps += 1000
        if self.cancelled and self.cancelled():
            self.reason = "cancelled"
        elif time.monotonic() >= self.deadline:
            self.reason = "time budget exceeded"
        elif self.steps > 2_000_000:
            self.reason = "VM instruction budget exceeded"
        return int(self.reason is not None)

    def check(self):
        if self.cancelled and self.cancelled():
            self.reason = "cancelled"
        elif time.monotonic() >= self.deadline:
            self.reason = "time budget exceeded"
        if self.reason:
            raise ValueError("SQLite inspection " + self.reason)


def file_budget(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("SQLite input must be an ordinary existing file")
    total = 0
    for suffix, limit in [
        ("", MAX_DATABASE),
        ("-wal", MAX_DATABASE),
        ("-shm", 1024 * 1024),
        ("-journal", MAX_DATABASE),
    ]:
        item = Path(str(path) + suffix)
        if item.is_symlink():
            raise ValueError("SQLite sidecar symlinks are unsupported")
        if item.exists():
            if not item.is_file() or item.stat().st_size > limit:
                raise ValueError("SQLite file or sidecar exceeds its byte budget")
            total += item.stat().st_size
    return total


@contextmanager
def reader(path, *, timeout=2, should_cancel=None):
    file_budget(path)
    budget = Budget(timeout, should_cancel)
    budget.check()
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=0.1)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        if hasattr(db, "enable_load_extension"):
            db.enable_load_extension(False)
        for category, limit in [
            ("SQLITE_LIMIT_LENGTH", 262144),
            ("SQLITE_LIMIT_SQL_LENGTH", 65536),
            ("SQLITE_LIMIT_COLUMN", 128),
            ("SQLITE_LIMIT_EXPR_DEPTH", 100),
            ("SQLITE_LIMIT_VARIABLE_NUMBER", 1000),
            ("SQLITE_LIMIT_COMPOUND_SELECT", 20),
        ]:
            if hasattr(db, "setlimit"):
                db.setlimit(getattr(sqlite3, category), limit)
        db.set_progress_handler(budget.progress, 1000)
        db.execute("BEGIN")
        # Establish the read snapshot before any related schema/data query.
        db.execute("SELECT count(*) FROM sqlite_schema").fetchone()
        try:
            yield db, budget
            budget.check()
        except sqlite3.Error as error:
            if budget.reason:
                raise ValueError("SQLite inspection " + budget.reason) from error
            raise ValueError("SQLite inspection failed: " + str(error)) from error
        finally:
            db.set_authorizer(None)
            db.set_progress_handler(None, 0)


def compile_queries(definitions):
    validate_json(definitions, max_bytes=1024 * 1024, max_depth=20, max_nodes=50000)
    if not isinstance(definitions, list) or not 1 <= len(definitions) <= 32:
        raise ValueError("SQLite checks require 1–32 query definitions")
    output = []
    ids = set()
    for item in definitions:
        if (
            not isinstance(item, dict)
            or set(item) - {"id", "sql", "parameters", "expected", "order"}
            or not {"id", "sql", "expected"} <= set(item)
        ):
            raise ValueError("SQLite query requires id, sql and expected rows")
        from .sqlite_seed import name

        label = name(item["id"])
        if label in ids:
            raise ValueError("SQLite query IDs must be unique")
        ids.add(label)
        sql = item["sql"]
        if (
            not isinstance(sql, str)
            or not sql.strip()
            or len(sql.encode()) > 65536
            or "\x00" in sql
        ):
            raise ValueError("SQLite query SQL must contain bounded text")
        parameters = item.get("parameters", [])
        if not isinstance(parameters, list) or len(parameters) > 1000:
            raise ValueError(
                "SQLite query supports at most 1,000 positional parameters"
            )
        for value in parameters:
            sqlite_value(value)
        expected = item["expected"]
        if (
            not isinstance(expected, list)
            or len(expected) > 1000
            or any(
                not isinstance(row, dict) or not 1 <= len(row) <= 64 for row in expected
            )
        ):
            raise ValueError(
                "SQLite expected results require at most 1,000 row objects"
            )
        keys = None
        for row in expected:
            if any(
                not isinstance(key, str) or not key or len(key) > 128 for key in row
            ):
                raise ValueError("SQLite result aliases require bounded names")
            if keys is not None and set(row) != keys:
                raise ValueError("expected query rows must share the same aliases")
            keys = set(row)
            for value in row.values():
                sqlite_value(value)
        order = item.get("order", "ordered")
        if not isinstance(order, str) or order not in {"ordered", "unordered"}:
            raise ValueError("query order must be ordered or unordered")
        output.append(
            {
                "id": label,
                "sql": sql,
                "parameters": copy.deepcopy(parameters),
                "expected": copy.deepcopy(expected),
                "order": order,
            }
        )
    return tuple(output)


def authorize(action, left, right, database, origin):
    if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ}:
        return sqlite3.SQLITE_OK
    if (
        action == sqlite3.SQLITE_FUNCTION
        and isinstance(right, str)
        and right.lower() in FUNCTIONS
    ):
        return sqlite3.SQLITE_OK
    # Recursive CTE reads are permitted, but bounded by the VM/time budgets.
    if action == getattr(sqlite3, "SQLITE_RECURSIVE", -1):
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def typed_row(row):
    return {key: typed(value) for key, value in row.items()}


def check_queries(path, definitions, *, timeout=2, should_cancel=None, _view=None):
    definitions = compile_queries(list(definitions))
    reports = []
    with (
        nullcontext(_view)
        if _view is not None
        else reader(path, timeout=timeout, should_cancel=should_cancel)
    ) as (db, budget):
        db.set_authorizer(authorize)
        for item in definitions:
            budget.check()
            report = {
                "id": item["id"],
                "passed": False,
                "query_sha256": identity(
                    {"sql": item["sql"], "parameters": item["parameters"]}
                ),
                "order": item["order"],
            }
            try:
                cursor = db.execute(
                    item["sql"], tuple(sqlite_value(v) for v in item["parameters"])
                )
                if cursor.description is None:
                    raise ValueError("SQLite checks must produce a read-only row set")
                columns = [column[0] for column in cursor.description]
                if (
                    not 1 <= len(columns) <= 64
                    or len(set(columns)) != len(columns)
                    or any(not col or len(col) > 128 for col in columns)
                ):
                    raise ValueError("query columns require distinct bounded aliases")
                actual = []
                actual_bytes = 2
                for values in cursor:
                    budget.check()
                    if len(actual) >= 1000:
                        raise ValueError("SQLite query result exceeds 1,000 rows")
                    row = typed_row(dict(zip(columns, values)))
                    actual_bytes += len(canonical(row)) + 1
                    if actual_bytes > 1024 * 1024:
                        raise ValueError("SQLite query result exceeds 1 MiB")
                    actual.append(row)
                expected = [
                    typed_row({key: sqlite_value(value) for key, value in row.items()})
                    for row in item["expected"]
                ]
                actual_keys = [canonical(row) for row in actual]
                expected_keys = [canonical(row) for row in expected]
                passed = (
                    actual_keys == expected_keys
                    if item["order"] == "ordered"
                    else Counter(actual_keys) == Counter(expected_keys)
                )
                report.update(
                    passed=passed,
                    columns=columns,
                    row_count=len(actual),
                    actual_sha256=identity(actual),
                    expected_sha256=identity(expected),
                    actual=actual[:20],
                    expected=expected[:20],
                    diagnostics_complete=len(actual) <= 20 and len(expected) <= 20,
                )
            except (sqlite3.Error, ValueError) as error:
                report["error"] = (
                    ("SQLite inspection " + budget.reason)
                    if budget.reason
                    else str(error)
                )
            reports.append(report)
            budget.check()
        db.set_authorizer(None)
    return {"passed": all(item["passed"] for item in reports), "queries": reports}


def database_snapshot(path, *, timeout=2, should_cancel=None, _view=None):
    with (
        nullcontext(_view)
        if _view is not None
        else reader(path, timeout=timeout, should_cancel=should_cancel)
    ) as (db, budget):
        objects = db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        ).fetchmany(257)
        if len(objects) > 256:
            raise ValueError("SQLite schema exceeds 256 objects")
        schema = [dict(zip(["type", "name", "table", "sql"], row)) for row in objects]
        tables = {}
        encoded_bytes = len(canonical(schema))
        total_rows = 0
        cells = 0
        for item in schema:
            budget.check()
            if item["type"] != "table":
                continue
            if item["sql"] is None or "CREATE VIRTUAL TABLE" in item["sql"].upper():
                raise ValueError(
                    "virtual tables and unavailable schema text are unsupported"
                )
            if len(tables) >= 64:
                raise ValueError("SQLite snapshot exceeds 64 tables")
            columns = db.execute(
                "PRAGMA table_xinfo(" + quoted(item["name"]) + ")"
            ).fetchall()
            if not 1 <= len(columns) <= 64:
                raise ValueError("SQLite snapshot table exceeds column limits")
            column_schema = [
                dict(
                    zip(
                        [
                            "cid",
                            "name",
                            "declared_type",
                            "not_null",
                            "default",
                            "primary_key",
                            "hidden",
                        ],
                        row,
                    )
                )
                for row in columns
            ]
            names = [row["name"] for row in column_schema]
            cursor = db.execute(
                "SELECT "
                + ",".join(map(quoted, names))
                + " FROM "
                + quoted(item["name"])
            )
            encoded = []
            for row in cursor:
                budget.check()
                total_rows += 1
                cells += len(names)
                if len(encoded) >= 10000 or total_rows > 20000 or cells > 100000:
                    raise ValueError("SQLite snapshot exceeds row/cell limits")
                value = typed_row(dict(zip(names, row)))
                encoded_bytes += len(canonical(value)) + 1
                if encoded_bytes > 16 * 1024 * 1024:
                    raise ValueError("SQLite logical snapshot exceeds 16 MiB")
                encoded.append(value)
            encoded.sort(key=canonical)
            tables[item["name"]] = {
                "columns": column_schema,
                "rows": encoded,
                "sha256": identity(encoded),
            }
        integrity = [row[0] for row in db.execute("PRAGMA quick_check").fetchmany(21)]
        foreign = [
            list(row) for row in db.execute("PRAGMA foreign_key_check").fetchmany(21)
        ]
        if integrity != ["ok"] or foreign:
            raise ValueError("SQLite integrity or foreign-key check failed")
        result = {
            "format": "reprolattice.sqlite-snapshot.v1",
            "schema": schema,
            "tables": tables,
        }
        if len(canonical(result)) > 16 * 1024 * 1024:
            raise ValueError("SQLite logical snapshot exceeds 16 MiB")
        result["sha256"] = identity(result)
        verify_database_snapshot(result)
        return result


def verify_database_snapshot(snapshot):
    validate_json(snapshot, max_bytes=16 * 1024 * 1024, max_depth=30, max_nodes=1000000)
    if (
        not isinstance(snapshot, dict)
        or set(snapshot) != {"format", "schema", "tables", "sha256"}
        or snapshot["format"] != "reprolattice.sqlite-snapshot.v1"
    ):
        raise ValueError("unsupported SQLite snapshot")
    if (
        identity({key: value for key, value in snapshot.items() if key != "sha256"})
        != snapshot["sha256"]
    ):
        raise ValueError("SQLite snapshot identity mismatch")
    if (
        not isinstance(snapshot["schema"], list)
        or len(snapshot["schema"]) > 256
        or not isinstance(snapshot["tables"], dict)
        or len(snapshot["tables"]) > 64
    ):
        raise ValueError("invalid SQLite snapshot schema")
    total = 0
    cells = 0
    schema_tables = set()
    for item in snapshot["schema"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"type", "name", "table", "sql"}
            or not isinstance(item["type"], str)
            or item["type"] not in {"table", "index", "view", "trigger"}
            or not all(isinstance(item[key], str) for key in ["name", "table", "sql"])
        ):
            raise ValueError("invalid SQLite schema object")
        if item["type"] == "table":
            schema_tables.add(item["name"])
    if schema_tables != set(snapshot["tables"]):
        raise ValueError("SQLite snapshot table/schema mismatch")
    for table in snapshot["tables"].values():
        if (
            not isinstance(table, dict)
            or set(table) != {"columns", "rows", "sha256"}
            or not isinstance(table["columns"], list)
            or not 1 <= len(table["columns"]) <= 64
            or not isinstance(table["rows"], list)
            or len(table["rows"]) > 10000
        ):
            raise ValueError("invalid SQLite table snapshot")
        columns = []
        for col in table["columns"]:
            if (
                not isinstance(col, dict)
                or set(col)
                != {
                    "cid",
                    "name",
                    "declared_type",
                    "not_null",
                    "default",
                    "primary_key",
                    "hidden",
                }
                or not isinstance(col["name"], str)
            ):
                raise ValueError("invalid SQLite snapshot column")
            columns.append(col["name"])
        if len(set(columns)) != len(columns):
            raise ValueError("duplicate SQLite snapshot columns")
        total += len(table["rows"])
        cells += len(columns) * len(table["rows"])
        for row in table["rows"]:
            if not isinstance(row, dict) or set(row) != set(columns):
                raise ValueError("SQLite snapshot row/column mismatch")
            for value in row.values():
                if not isinstance(value, dict) or set(value) != {"type", "value"}:
                    raise ValueError("invalid typed SQLite snapshot cell")
                kind = value["type"]
                raw = value["value"]
                converted = (
                    sqlite_value({"$blob": raw})
                    if kind == "blob"
                    else sqlite_value(raw)
                )
                if typed(converted) != value:
                    raise ValueError("SQLite snapshot storage type mismatch")
        if (
            table["rows"] != sorted(table["rows"], key=canonical)
            or identity(table["rows"]) != table["sha256"]
        ):
            raise ValueError("SQLite snapshot rows are changed or not canonical")
    if total > 20000 or cells > 100000:
        raise ValueError("SQLite snapshot row/cell budget exceeded")
    return snapshot


