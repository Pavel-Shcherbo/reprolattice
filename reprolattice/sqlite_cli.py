"""Create fixtures, inspect SQLite state and compare portable logical snapshots."""

import argparse
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from .jsonutil import strict_json
from .sqlite_seed import canonical, create_database
from .sqlite_inspect import (
    check_queries,
    database_snapshot,
    compare_snapshots,
    verify_database_snapshot,
)


def load(path, limit):
    with Path(path).open("rb") as stream:
        return strict_json(stream.read(limit + 1), max_bytes=limit)


def save_snapshot(snapshot, path):
    verify_database_snapshot(snapshot)
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".sqlite-snapshot-", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(canonical(snapshot) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"path": str(path), "sha256": snapshot["sha256"]}


def main():
    parser = argparse.ArgumentParser(
        description="Inspect local SQLite application state without executing write SQL"
    )
    commands = parser.add_subparsers(dest="action", required=True)
    seed = commands.add_parser("seed")
    seed.add_argument("definition", type=Path)
    seed.add_argument("database", type=Path)
    snap = commands.add_parser("snapshot")
    snap.add_argument("database", type=Path)
    snap.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("check")
    check.add_argument("database", type=Path)
    check.add_argument("checks", type=Path)
    diff = commands.add_parser("compare")
    diff.add_argument("before", type=Path)
    diff.add_argument("after", type=Path)
    verify = commands.add_parser("verify-snapshot")
    verify.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "seed":
            result = create_database(
                load(args.definition, 4 * 1024 * 1024), args.database
            )
        elif args.action == "snapshot":
            result = save_snapshot(database_snapshot(args.database), args.output)
        elif args.action == "check":
            result = check_queries(args.database, load(args.checks, 1024 * 1024))
        elif args.action == "compare":
            result = compare_snapshots(
                load(args.before, 16 * 1024 * 1024), load(args.after, 16 * 1024 * 1024)
            )
        else:
            snapshot = verify_database_snapshot(load(args.snapshot, 16 * 1024 * 1024))
            result = {"passed": True, "sha256": snapshot["sha256"]}
        print(json.dumps(result, indent=2, allow_nan=False))
        return 1 if result.get("passed") is False or result.get("equal") is False else 0
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        sqlite3.Error,
        OverflowError,
    ) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
