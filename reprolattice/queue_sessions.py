"""Author, inspect and export saved queue histories from the local command line."""

import argparse
import json
from pathlib import Path
import sqlite3

from .jsonutil import strict_json
from .queue_lab import QueueLab, MAX_DOCUMENT, verify_export
from .queue_model import canonical


def load(path):
    with Path(path).open("rb") as stream:
        return strict_json(
            stream.read(MAX_DOCUMENT + 1), max_bytes=MAX_DOCUMENT, max_nodes=4000000
        )


def main():
    cli = argparse.ArgumentParser(
        description="Saved local queue simulations and reviewed worker controls"
    )
    cli.add_argument(
        "--database", type=Path, default=Path(".local/queue-workbench/queues.sqlite")
    )
    cli.add_argument("--project", default="local")
    commands = cli.add_subparsers(dest="action", required=True)
    listing = commands.add_parser("list")
    listing.add_argument("--before", type=int, default=0)
    create = commands.add_parser("create")
    create.add_argument("configuration", type=Path)
    imported = commands.add_parser("import")
    imported.add_argument("evidence", type=Path)
    fork = commands.add_parser("fork")
    fork.add_argument("record")
    fork.add_argument("--generation", type=int, required=True)
    fork.add_argument("--case")
    workers = commands.add_parser("workers")
    for command in (create, imported, fork, workers):
        command.add_argument("--label", required=True)
        command.add_argument("--request-key", required=True)
    execute = commands.add_parser("commands")
    execute.add_argument("record")
    execute.add_argument("commands", type=Path)
    execute.add_argument("--generation", type=int, required=True)
    execute.add_argument("--request-key", required=True)
    view = commands.add_parser("view")
    view.add_argument("record")
    view.add_argument("--generation", type=int)
    view.add_argument("--after", type=int, default=0)
    view.add_argument("--message-offset", type=int, default=0)
    view.add_argument("--case")
    receipt = commands.add_parser("receipt")
    receipt.add_argument("request_key")
    export = commands.add_parser("export")
    export.add_argument("record")
    export.add_argument("--generation", type=int, required=True)
    export.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("file", type=Path)
    args = cli.parse_args()
    try:
        if args.action == "verify":
            result = verify_export(load(args.file))
        else:
            lab = QueueLab(args.database)
            if args.action == "list":
                result = lab.list(args.project, before=args.before)
            elif args.action == "view":
                result = lab.view(
                    args.project,
                    args.record,
                    generation=args.generation,
                    after=args.after,
                    message_offset=args.message_offset,
                    case=args.case,
                )
            elif args.action == "receipt":
                result = lab.receipt(args.project, args.request_key)
            elif args.action == "export":
                value = lab.export(args.project, args.record, args.generation)
                with args.output.open("xb") as stream:
                    stream.write(canonical(value) + b"\n")
                args.output.chmod(0o600)
                result = {"path": str(args.output), "sha256": value["sha256"]}
            else:
                payload = {}
                if args.action in ("create", "import", "fork", "workers"):
                    payload["label"] = args.label
                if args.action == "create":
                    payload["configuration"] = load(args.configuration)
                if args.action == "import":
                    payload["evidence"] = load(args.evidence)
                if args.action in ("commands", "fork"):
                    payload.update(record=args.record, generation=args.generation)
                    if args.action == "commands":
                        payload["commands"] = load(args.commands)
                    elif args.case is not None:
                        payload["case"] = args.case
                result = lab.apply(args.project, args.request_key, args.action, payload)
        print(json.dumps(result, indent=2, allow_nan=False))
        if result.get("replay", {}).get("complete") is False:
            return 1
        return 0
    except (ValueError, TypeError, KeyError, OSError, sqlite3.Error) as error:
        cli.exit(2, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
