"""Qualify reversible SQLite migrations on isolated copies and replay evidence."""

import argparse
import json
from pathlib import Path
import sqlite3

from .jsonutil import strict_json
from .migration_bundle import verify_migration_bundle
from .migration_runner import qualify_migrations


def load(path):
    with path.open("rb") as stream:
        return strict_json(
            stream.read(4 * 1024 * 1024 + 1),
            max_bytes=4 * 1024 * 1024,
            max_nodes=250000,
        )


def main():
    parser = argparse.ArgumentParser(
        description="Rehearse SQLite migration SQL without writing to the source database"
    )
    sub = parser.add_subparsers(dest="action", required=True)
    run = sub.add_parser("run")
    run.add_argument("plan", type=Path)
    run.add_argument("--output", type=Path, required=True)
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--seed", type=Path)
    source.add_argument("--source", type=Path)
    verify = sub.add_parser("verify")
    verify.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "run":
            result = qualify_migrations(
                load(args.plan),
                args.output,
                seed=load(args.seed) if args.seed else None,
                source=args.source,
            )
        else:
            result = verify_migration_bundle(args.directory)
        print(json.dumps(result, indent=2, allow_nan=False))
        return (
            0
            if result.get("qualification_passed") and result.get("passed", True)
            else 1
        )
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
