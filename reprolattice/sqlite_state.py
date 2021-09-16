"""SQLite state setup and postconditions shared by suite execution and CLI."""

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .jsonutil import strict_json
from .sqlite_seed import canonical, compile_seed, create_database, identity
from .sqlite_inspect import check_queries, compare_snapshots, database_snapshot, reader


@dataclass(frozen=True)
class SQLiteState:
    path: str
    seed: dict
    queries: tuple
    sha256: str
    input_bytes: int


def compile_states(definitions, root="."):
    from .suite_config import relative_path, rooted, read_bounded, SHA

    if not isinstance(definitions, list) or len(definitions) > 4:
        raise ValueError("case SQLite states support at most four databases")
    output = []
    seen = set()
    for item in definitions:
        if (
            not isinstance(item, dict)
            or set(item) - {"path", "seed", "seed_sha256", "checks"}
            or not {"path", "seed", "checks"} <= set(item)
        ):
            raise ValueError("SQLite state requires path, seed and checks")
        path = relative_path(item["path"])
        key = str(Path(path)).casefold()
        if key in seen:
            raise ValueError("SQLite state paths must be unique")
        seen.add(key)
        if isinstance(item["seed"], str):
            raw = read_bounded(rooted(root, item["seed"]), 4 * 1024 * 1024)
            expected = item.get("seed_sha256")
            if expected is not None and (
                not isinstance(expected, str)
                or not SHA.fullmatch(expected)
                or hashlib.sha256(raw).hexdigest() != expected
            ):
                raise ValueError("SQLite seed differs from its pinned SHA-256")
            definition = strict_json(raw, max_bytes=4 * 1024 * 1024)
        else:
            if "seed_sha256" in item:
                raise ValueError("seed_sha256 applies only to file seeds")
            definition = item["seed"]
        seed = compile_seed(definition)
        checks = check_definitions(item["checks"])
        payload = {"path": path, "seed": seed, "checks": checks}
        output.append(
            SQLiteState(path, seed, checks, identity(payload), len(canonical(payload)))
        )
    return tuple(output)


def check_definitions(definitions):
    from .sqlite_inspect import compile_queries

    return compile_queries(definitions)


