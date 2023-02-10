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


def prepare_states(workspace, definitions, *, should_cancel=None):
    workspace = Path(workspace).resolve()
    prepared = []
    for state in definitions:
        if should_cancel and should_cancel():
            raise ValueError("SQLite state setup cancelled")
        target = workspace / state.path
        target.parent.mkdir(parents=True, exist_ok=True)
        create_database(state.seed, target)
        before = database_snapshot(target, should_cancel=should_cancel)
        prepared.append((state, before))
    return prepared


def inspect_states(workspace, prepared, *, should_cancel=None, on_snapshot=None):
    from .suite_config import rooted

    workspace = Path(workspace).resolve()
    reports = []
    for state, before in prepared:
        report = {
            "path": state.path,
            "definition_sha256": state.sha256,
            "passed": False,
            "before_sha256": before["sha256"],
        }
        try:
            lexical = workspace / state.path
            if any(
                part.is_symlink()
                for part in [lexical, *lexical.parents]
                if part.is_relative_to(workspace)
            ):
                raise ValueError("SQLite state symlinks are unsupported")
            target = rooted(workspace, state.path)
            # Application is stopped by the harness before these bounded reads.
            with reader(target, should_cancel=should_cancel) as view:
                checks = check_queries(target, state.queries, _view=view)
                after = database_snapshot(target, _view=view)
            if on_snapshot is not None:
                on_snapshot(state, before, after)
            report.update(
                passed=checks["passed"],
                checks=checks,
                after_sha256=after["sha256"],
                changes=compare_snapshots(before, after),
            )
        except (ValueError, OSError, sqlite3.Error) as error:
            report["error"] = str(error)
        reports.append(report)
    return reports
