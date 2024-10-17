"""Retain local migration rehearsals and verify their portable archive envelopes."""

import argparse
import json
from pathlib import Path
import sqlite3

from .migration_archive import MigrationArchive
from .migration_views import (
    inspect_rehearsal,
    export_rehearsal,
    verify_retained_migration,
    MAX_EXPORT,
)
from .jsonutil import strict_json
from .migrations import load
from .sqlite_seed import canonical


def main():
    cli = argparse.ArgumentParser(
        description="Retain scoped isolated migration rehearsals"
    )
    cli.add_argument("--archive", type=Path, default=Path(".local/migration-runs"))
    cli.add_argument("--project", default="local")
    actions = cli.add_subparsers(dest="action", required=True)
    run = actions.add_parser("run")
    run.add_argument("plan", type=Path)
    run.add_argument("--seed", type=Path, required=True)
    run.add_argument("--request-key", required=True)
    run.add_argument("--label", default="")
    listing = actions.add_parser("list")
    listing.add_argument("--after", type=int, default=0)
    for name in ("inspect", "export", "recover"):
        sub = actions.add_parser(name)
        sub.add_argument("record")
        if name == "export":
            sub.add_argument("--output", type=Path, required=True)
        if name == "recover":
            sub.add_argument("--generation", type=int, required=True)
    verify = actions.add_parser("verify")
    verify.add_argument("file", type=Path)
    args = cli.parse_args()
    try:
        if args.action == "verify":
            with args.file.open("rb") as stream:
                document = strict_json(
                    stream.read(MAX_EXPORT + 1), max_bytes=MAX_EXPORT, max_nodes=200000
                )
            result = verify_retained_migration(document)
        else:
            archive = MigrationArchive(args.archive)
            if args.action == "run":
                result = archive.run(
                    args.project,
                    load(args.plan),
                    load(args.seed),
                    args.request_key,
                    args.label,
                )
            elif args.action == "list":
                result = archive.list(args.project, after=args.after)
            elif args.action == "inspect":
                result = inspect_rehearsal(archive, args.project, args.record)
            elif args.action == "recover":
                result = archive.recover(args.project, args.record, args.generation)
            else:
                document = export_rehearsal(archive, args.project, args.record)
                with args.output.open("xb") as stream:
                    stream.write(canonical(document) + b"\n")
                args.output.chmod(0o600)
                result = {"path": str(args.output), "sha256": document["sha256"]}
        print(json.dumps(result, indent=2))
        if (
            result.get("qualification_passed") is False
            or (result.get("report") or {}).get("qualification_passed") is False
        ):
            return 1
        if (
            isinstance(result.get("record"), dict)
            and result["record"].get("status", "completed") != "completed"
        ):
            return 1
        return 0
    except (ValueError, TypeError, KeyError, OSError, sqlite3.Error) as error:
        cli.exit(2, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
