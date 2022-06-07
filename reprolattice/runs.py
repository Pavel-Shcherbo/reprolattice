"""Archive local suite runs, control named baselines and explain comparison gates."""

import argparse
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from .jsonutil import strict_json
from .run_registry import RunRegistry
from .run_contract import fingerprint
from .suite_config import read_bounded


def save_comparison(result, path):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".run-comparison-", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(
                (json.dumps(result, indent=2, allow_nan=False) + "\n").encode()
            )
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(
        description="Retain immutable local suite evidence and compare recorded outcomes"
    )
    parser.add_argument("--database", type=Path, default=Path(".local/runs.sqlite"))
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("init")
    project = commands.add_parser("project-create")
    project.add_argument("project")
    record = commands.add_parser("record")
    record.add_argument("project")
    record.add_argument("report", type=Path)
    record.add_argument("--revision", required=True)
    record.add_argument("--request-key", required=True)
    record.add_argument("--label", default="")
    record.add_argument("--context", type=Path)
    listing = commands.add_parser("list")
    listing.add_argument("project")
    listing.add_argument("--after", type=int, default=0)
    listing.add_argument("--limit", type=int, default=100)
    listing.add_argument("--suite")
    get = commands.add_parser("get")
    get.add_argument("project")
    get.add_argument("record")
    baseline = commands.add_parser("baseline")
    baseline.add_argument("project")
    baseline.add_argument("name")
    move = commands.add_parser("baseline-move")
    move.add_argument("project")
    move.add_argument("name")
    move.add_argument("record")
    move.add_argument("--expected-generation", type=int, required=True)
    move.add_argument("--reason", required=True)
    history = commands.add_parser("case-history")
    history.add_argument("project")
    history.add_argument("source_id")
    history.add_argument("--after", type=int, default=0)
    history.add_argument("--limit", type=int, default=100)
    history.add_argument("--status")
    moves = commands.add_parser("baseline-history")
    moves.add_argument("project")
    moves.add_argument("name")
    moves.add_argument("--after", type=int, default=0)
    moves.add_argument("--limit", type=int, default=100)
    compare = commands.add_parser("compare")
    compare.add_argument("project")
    compare.add_argument("before")
    compare.add_argument("after")
    compare.add_argument(
        "--baseline", action="store_true", help="Resolve BEFORE as a named baseline"
    )
    compare.add_argument("--policy", type=Path)
    compare.add_argument("--output", type=Path)
    export = commands.add_parser("export")
    export.add_argument("project")
    export.add_argument("record")
    export.add_argument("--output", type=Path, required=True)
    audit = commands.add_parser("audit")
    audit.add_argument("project")
    audit.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()

    def definition(path, limit):
        return strict_json(read_bounded(path, limit), max_bytes=limit)

    try:
        registry = RunRegistry(args.database, create=args.action == "init")
        if args.action == "init":
            result = {
                "database": str(registry.path),
                "store_id": registry.id,
                "initialized": True,
            }
        elif args.action == "project-create":
            result = registry.project(args.project)
        elif args.action == "record":
            result = registry.record(
                args.project,
                definition(args.report, 8 * 1024 * 1024),
                revision=args.revision,
                request_key=args.request_key,
                label=args.label,
                run_context=definition(args.context, 16384) if args.context else None,
            )
        elif args.action == "list":
            result = registry.list(
                args.project, after=args.after, limit=args.limit, suite=args.suite
            )
        elif args.action == "get":
            result = registry.get(args.project, args.record)
        elif args.action == "baseline":
            result = registry.baseline(args.project, args.name)
        elif args.action == "baseline-move":
            result = registry.move_baseline(
                args.project,
                args.name,
                args.record,
                expected_generation=args.expected_generation,
                reason=args.reason,
            )
        elif args.action == "case-history":
            result = registry.history(
                args.project,
                args.source_id,
                after=args.after,
                limit=args.limit,
                status=args.status,
            )
        elif args.action == "baseline-history":
            result = registry.baseline_history(
                args.project, args.name, after=args.after, limit=args.limit
            )
        elif args.action == "compare":
            baseline = (
                registry.baseline(args.project, args.before) if args.baseline else None
            )
            result = registry.compare(
                args.project,
                baseline["record_id"] if baseline else args.before,
                args.after,
                policy=definition(args.policy, 16384) if args.policy else None,
            )
            if baseline is not None:
                result.pop("sha256")
                result["baseline_resolution"] = baseline
                result["sha256"] = fingerprint(result)
            if args.output:
                save_comparison(result, args.output)
        elif args.action == "export":
            result = registry.export(args.project, args.record, args.output)
        else:
            result = registry.audit(args.project, limit=args.limit)
        print(json.dumps(result, indent=2, allow_nan=False))
        return (
            1
            if args.action == "audit"
            and result.get("passed") is False
            or args.action == "compare"
            and result.get("gate", {}).get("passed") is False
            else 0
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
