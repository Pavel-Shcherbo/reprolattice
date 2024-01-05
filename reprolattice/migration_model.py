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


