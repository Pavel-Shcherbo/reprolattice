"""Structured, constrained SQLite fixtures published without overwriting files."""

import copy
import hashlib
import json
import math
import os
import re
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from .jsonutil import validate_json

NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
TYPES = {"INTEGER", "REAL", "TEXT", "BLOB"}
MAX_DATABASE = 16 * 1024 * 1024


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode()


def identity(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def name(value):
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise ValueError(
            "SQLite fixture identifiers require at most 64 ASCII letters, digits or underscores"
        )
    return value


def quoted(value):
    return '"' + value.replace('"', '""') + '"'


def sqlite_value(value):
    if isinstance(value, dict) and set(value) == {"$blob"}:
        encoded = value["$blob"]
        if (
            not isinstance(encoded, str)
            or len(encoded) > 131072
            or not re.fullmatch(r"(?:[0-9a-f]{2})*", encoded)
        ):
            raise ValueError(
                "BLOB values require bounded lowercase even-length hexadecimal"
            )
        return bytes.fromhex(encoded)
    if value is None or type(value) in {str, int, float}:
        if type(value) is int and not -(2**63) <= value < 2**63:
            raise ValueError("SQLite integer exceeds signed 64-bit range")
        if type(value) is float and not math.isfinite(value):
            raise ValueError("SQLite real must be finite")
        if isinstance(value, str) and len(value.encode()) > 65536:
            raise ValueError("SQLite text exceeds 64 KiB")
        return value
    raise ValueError(
        "SQLite values require null, integer, real, text or an explicit BLOB"
    )


def typed(value):
    if value is None:
        return {"type": "null", "value": None}
    if type(value) is int:
        return {"type": "integer", "value": value}
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("non-finite SQLite result")
        return {"type": "real", "value": value}
    if isinstance(value, str):
        if len(value.encode()) > 65536:
            raise ValueError("SQLite result text exceeds 64 KiB")
        return {"type": "text", "value": value}
    if isinstance(value, bytes):
        if len(value) > 65536:
            raise ValueError("SQLite result BLOB exceeds 64 KiB")
        return {"type": "blob", "value": value.hex()}
    raise ValueError("unsupported SQLite storage value")


def column_list(value, columns, label, *, allow_empty=False):
    if (
        not isinstance(value, list)
        or not (0 if allow_empty else 1) <= len(value) <= len(columns)
        or any(not isinstance(item, str) for item in value)
        or len(set(value)) != len(value)
        or not set(value) <= set(columns)
    ):
        raise ValueError(f"{label} requires distinct declared column names")
    return value


def compile_seed(definition):
    validate_json(definition, max_bytes=4 * 1024 * 1024, max_nodes=200000, max_depth=20)
    if (
        not isinstance(definition, dict)
        or set(definition) != {"version", "tables"}
        or type(definition["version"]) is not int
        or definition["version"] != 1
    ):
        raise ValueError("SQLite seed requires version 1 and tables")
    tables = definition["tables"]
    if not isinstance(tables, list) or not 1 <= len(tables) <= 32:
        raise ValueError("SQLite seed requires 1–32 tables")
    result = copy.deepcopy(definition)
    declared = {}
    cells = 0
    rows_total = 0
    for table in result["tables"]:
        if (
            not isinstance(table, dict)
            or set(table)
            - {"name", "columns", "rows", "primary_key", "unique", "foreign_keys"}
            or not {"name", "columns", "rows"} <= set(table)
        ):
            raise ValueError("unsupported SQLite table fields")
        table_name = name(table["name"])
        if table_name.lower().startswith("sqlite_") or table_name.lower() in declared:
            raise ValueError("reserved or case-insensitively duplicate table name")
        columns = table["columns"]
        if not isinstance(columns, list) or not 1 <= len(columns) <= 64:
            raise ValueError("table requires 1–64 columns")
        by_name = {}
        folded = set()
        for column in columns:
            if not isinstance(column, dict) or set(column) != {
                "name",
                "type",
                "nullable",
            }:
                raise ValueError("columns require name, type and nullable")
            col = name(column["name"])
            if (
                col.lower() in folded
                or not isinstance(column["type"], str)
                or column["type"] not in TYPES
                or type(column["nullable"]) is not bool
            ):
                raise ValueError("invalid, duplicate or unsupported SQLite column")
            folded.add(col.lower())
            by_name[col] = column
        primary = column_list(
            table.setdefault("primary_key", []),
            by_name,
            "primary key",
            allow_empty=True,
        )
        if any(by_name[col]["nullable"] for col in primary):
            raise ValueError("primary key columns must be explicitly non-nullable")
        unique = table.setdefault("unique", [])
        if not isinstance(unique, list) or len(unique) > 16:
            raise ValueError("at most 16 unique constraints are supported")
        for constraint in unique:
            column_list(constraint, by_name, "unique constraint")
        rows = table["rows"]
        if not isinstance(rows, list) or len(rows) > 10000:
            raise ValueError("table supports at most 10,000 seed rows")
        rows_total += len(rows)
        cells += len(rows) * len(columns)
        if rows_total > 20000 or cells > 100000:
            raise ValueError("SQLite seed row/cell budget exceeded")
        for row in rows:
            if not isinstance(row, dict) or set(row) != set(by_name):
                raise ValueError(
                    "seed rows must supply every declared column exactly once"
                )
            for col, column in by_name.items():
                value = sqlite_value(row[col])
                expected = {"INTEGER": int, "REAL": float, "TEXT": str, "BLOB": bytes}[
                    column["type"]
                ]
                if value is None:
                    if not column["nullable"]:
                        raise ValueError("null in a non-nullable seed column")
                elif type(value) is not expected:
                    raise ValueError(
                        "seed value storage type differs from the declared column type"
                    )
        declared[table_name.lower()] = table
    for table in result["tables"]:
        columns = {col["name"]: col for col in table["columns"]}
        foreign = table.setdefault("foreign_keys", [])
        if not isinstance(foreign, list) or len(foreign) > 16:
            raise ValueError("at most 16 foreign keys are supported per table")
        for key in foreign:
            if not isinstance(key, dict) or set(key) != {
                "columns",
                "table",
                "references",
                "on_delete",
            }:
                raise ValueError(
                    "foreign keys require columns, table, references and on_delete"
                )
            column_list(key["columns"], columns, "foreign key")
            target = declared.get(name(key["table"]).lower())
            if target is None or key["table"] != target["name"]:
                raise ValueError(
                    "foreign key target must name a declared table exactly"
                )
            target_columns = {col["name"]: col for col in target["columns"]}
            column_list(key["references"], target_columns, "foreign reference")
            if len(key["columns"]) != len(key["references"]) or key[
                "references"
            ] not in [target["primary_key"], *target["unique"]]:
                raise ValueError(
                    "foreign references require a matching primary/unique key"
                )
            if not isinstance(key["on_delete"], str) or key["on_delete"] not in {
                "RESTRICT",
                "CASCADE",
                "SET NULL",
            }:
                raise ValueError("unsupported foreign-key delete action")
            for left, right in zip(key["columns"], key["references"]):
                if columns[left]["type"] != target_columns[right]["type"]:
                    raise ValueError("foreign key column types must match")
                if key["on_delete"] == "SET NULL" and not columns[left]["nullable"]:
                    raise ValueError("SET NULL requires nullable child columns")
    # Validate relational constraints before any case can launch an application.
    for table in result["tables"]:
        for constraint in [table["primary_key"], *table["unique"]]:
            if not constraint:
                continue
            seen = set()
            for row in table["rows"]:
                key = tuple(sqlite_value(row[col]) for col in constraint)
                if any(value is None for value in key):
                    continue
                if key in seen:
                    raise ValueError("duplicate primary or unique seed key")
                seen.add(key)
        for foreign in table["foreign_keys"]:
            target = declared[foreign["table"].lower()]
            keys = {
                tuple(sqlite_value(row[col]) for col in foreign["references"])
                for row in target["rows"]
            }
            for row in table["rows"]:
                key = tuple(sqlite_value(row[col]) for col in foreign["columns"])
                if all(value is not None for value in key) and key not in keys:
                    raise ValueError("seed foreign key has no referenced row")
    return result


