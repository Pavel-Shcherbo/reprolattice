"""Opt-in retention and inspection of trusted local suites' SQLite states."""

import argparse
import json
from pathlib import Path
import sqlite3

from .jsonutil import strict_json
from .state_archive import StateArchive
from .state_service import execute_retained, inspect_record, inspect_table, inspect_diff
from .suite_config import compile_suite


def main():
    parser = argparse.ArgumentParser(
        description="Retain bounded raw SQLite state from a trusted local suite"
    )
    parser.add_argument("--database", type=Path)
    parser.add_argument("--project")
    sub = parser.add_subparsers(dest="action", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("document", type=Path)
    run = sub.add_parser("run")
    run.add_argument("suite", type=Path)
    run.add_argument("--request-key", required=True)
    run.add_argument("--label", default="")
    run.add_argument("--jobs", type=int, default=2)
    listing = sub.add_parser("list")
    listing.add_argument("--after", type=int, default=0)
    audit = sub.add_parser("audit")
    audit.add_argument("--after", type=int, default=0)
    for action in ("inspect", "export", "table", "diff"):
        command = sub.add_parser(action)
        command.add_argument("record")
        if action == "export":
            command.add_argument("--output", type=Path, required=True)
        if action in ("table", "diff"):
            command.add_argument("case")
            command.add_argument("path")
            command.add_argument("table")
            command.add_argument("--offset", type=int, default=0)
            command.add_argument("--limit", type=int, default=25)
            if action == "table":
                command.add_argument(
                    "--side", choices=("before", "after"), default="after"
                )
            else:
                command.add_argument(
                    "--status",
                    choices=(
                        "changed",
                        "all",
                        "added",
                        "removed",
                        "modified",
                        "unchanged",
                    ),
                    default="changed",
                )
    args = parser.parse_args()
    try:
        if args.action == "verify":
            from .state_evidence import MAX_EVIDENCE, verify_export

            with args.document.open("rb") as stream:
                value = strict_json(
                    stream.read(MAX_EVIDENCE + 65537),
                    max_bytes=MAX_EVIDENCE + 65536,
                    max_nodes=1800000,
                )
            print(json.dumps(verify_export(value), indent=2, allow_nan=False))
            return 0
        if args.database is None or args.project is None:
            raise ValueError("this state action requires --database and --project")
        plan = None
        if args.action == "run":
            with args.suite.open("rb") as stream:
                definition = strict_json(stream.read(1024 * 1024 + 1))
            plan = compile_suite(definition, args.suite.resolve().parent)
            from .state_evidence import ensure_retainable

            ensure_retainable(plan)
        archive = StateArchive(args.database, create=args.action == "run")
        if args.action == "run":
            result = execute_retained(
                plan,
                archive,
                args.project,
                request_key=args.request_key,
                label=args.label,
                jobs=args.jobs,
            )
        elif args.action == "list":
            result = archive.list(args.project, after=args.after)
        elif args.action == "audit":
            result = archive.audit(args.project, after=args.after)
        elif args.action == "inspect":
            result = inspect_record(archive, args.project, args.record)
        elif args.action == "table":
            result = inspect_table(
                archive,
                args.project,
                args.record,
                args.case,
                args.path,
                args.table,
                side=args.side,
                offset=args.offset,
                limit=args.limit,
            )
        elif args.action == "diff":
            result = inspect_diff(
                archive,
                args.project,
                args.record,
                args.case,
                args.path,
                args.table,
                status=args.status,
                offset=args.offset,
                limit=args.limit,
            )
        else:
            result = archive.get(args.project, args.record)
            created = False
            try:
                with args.output.open("x", encoding="utf-8") as stream:
                    created = True
                    stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
            except BaseException:
                if created:
                    args.output.unlink(missing_ok=True)
                raise
            result = {"path": str(args.output), "id": args.record}
        print(json.dumps(result, indent=2, allow_nan=False))
        if args.action == "run" and (
            not result["report"]["passed"] or not result["record"]["capture_complete"]
        ):
            return 1
        if args.action == "audit" and not result["passed"]:
            return 1
        return 0
    except (ValueError, TypeError, KeyError, OSError, sqlite3.Error) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
