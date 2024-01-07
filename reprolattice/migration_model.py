"""Immutable migration rehearsal contracts with explicit checks and reverse SQL."""

import copy
from dataclasses import dataclass

from .jsonutil import validate_json
from .sqlite_inspect import compile_queries
from .sqlite_seed import canonical, identity, name, sqlite_value

MAX_PLAN = 4 * 1024 * 1024
PREFIX = "_reprolattice_"


@dataclass(frozen=True)
class MigrationPlan:
    definition: dict
    sha256: str


def statements(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 64:
        raise ValueError("migration direction requires 1–64 single statements")
    output = []
    ids = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"id", "sql", "parameters"}:
            raise ValueError("migration statement requires id, sql and parameters")
        label = name(item["id"])
        if label in ids:
            raise ValueError("statement IDs must be unique within a direction")
        ids.add(label)
        sql = item["sql"]
        parameters = item["parameters"]
        if (
            not isinstance(sql, str)
            or not sql.strip()
            or "\0" in sql
            or len(sql.encode()) > 65536
        ):
            raise ValueError("migration SQL must be nonempty text within 64 KiB")
        if not isinstance(parameters, list) or len(parameters) > 1000:
            raise ValueError("migration statements support at most 1,000 bound values")
        for value in parameters:
            sqlite_value(value)
        output.append(
            {"id": label, "sql": sql, "parameters": copy.deepcopy(parameters)}
        )
    return output


def compile_migrations(value):
    validate_json(value, max_bytes=MAX_PLAN, max_depth=25, max_nodes=250000)
    if (
        not isinstance(value, dict)
        or set(value) != {"version", "name", "baseline_checks", "migrations"}
        or type(value["version"]) is not int
        or value["version"] != 1
    ):
        raise ValueError(
            "migration plan requires version 1, name, baseline_checks and migrations"
        )
    label = name(value["name"])
    steps = value["migrations"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= 16:
        raise ValueError("migration plan requires 1–16 ordered migrations")
    result = []
    ids = set()
    sql_bytes = 0
    for step in steps:
        if not isinstance(step, dict) or set(step) != {
            "id",
            "before_checks",
            "up",
            "after_checks",
            "down",
            "rollback_checks",
        }:
            raise ValueError(
                "migration requires id, before/after/rollback checks and up/down SQL"
            )
        identifier = name(step["id"])
        if identifier in ids:
            raise ValueError("migration IDs must be unique")
        ids.add(identifier)
        item = {"id": identifier}
        for key in ("before_checks", "after_checks", "rollback_checks"):
            item[key] = list(compile_queries(step[key]))
        for key in ("up", "down"):
            item[key] = statements(step[key])
            sql_bytes += sum(len(row["sql"].encode()) for row in item[key])
        result.append(item)
    if sql_bytes > 1024 * 1024:
        raise ValueError("combined migration SQL exceeds 1 MiB")
    definition = {
        "version": 1,
        "name": label,
        "baseline_checks": list(compile_queries(value["baseline_checks"])),
        "migrations": result,
    }
    return MigrationPlan(definition, identity(definition))


def compact_checks(report):
    result = copy.deepcopy(report)
    for query in result["queries"]:
        if "error" in query:
            query["error"] = query["error"][:512]
    if len(canonical(result)) > 32768:
        for query in result["queries"]:
            query.pop("actual", None)
            query.pop("expected", None)
            query["diagnostics_complete"] = False
        result["value_diagnostics_omitted"] = True
    return result
