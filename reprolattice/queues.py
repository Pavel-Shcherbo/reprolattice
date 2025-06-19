"""Run queue-backed application fixtures and verify retained broker evidence."""

import argparse
import json
import os
from pathlib import Path
import tempfile

from .jsonutil import strict_json
from .queue_engine import verify_queue_evidence
from .queue_harness import check_queue
from .queue_model import canonical, MAX_EVIDENCE


def write_evidence(document, path):
    verify_queue_evidence(document)
    raw = canonical(document) + b"\n"
    if len(raw) > MAX_EVIDENCE:
        raise ValueError("queue evidence exceeds 8 MiB")
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".queue-proof-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"path": str(path), "sha256": document["sha256"], "bytes": len(raw)}


def main():
    parser = argparse.ArgumentParser(
        description="Run a trusted worker against an isolated virtual-clock queue"
    )
    commands = parser.add_subparsers(dest="action", required=True)
    run = commands.add_parser("run")
    run.add_argument("fixture", type=Path)
    run.add_argument("--cwd", type=Path)
    run.add_argument("--timeout", type=float, default=10)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--command", nargs=argparse.REMAINDER, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("evidence", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "verify":
            with args.evidence.open("rb") as stream:
                value = strict_json(
                    stream.read(MAX_EVIDENCE + 1),
                    max_bytes=MAX_EVIDENCE,
                    max_nodes=4000000,
                )
            result = verify_queue_evidence(value)
            code = 0 if result["complete"] else 1
        else:
            if args.output.exists() or args.output.is_symlink():
                raise ValueError("queue evidence destination already exists")
            with args.fixture.open("rb") as stream:
                fixture = strict_json(
                    stream.read(2 * 1024 * 1024 + 1), max_bytes=2 * 1024 * 1024
                )
            result = check_queue(
                fixture, args.command, timeout=args.timeout, cwd=args.cwd
            )
            result["evidence"] = write_evidence(
                result.pop("queue_evidence"), args.output
            )
            code = 0 if result["passed"] else 1
        print(json.dumps(result, indent=2, allow_nan=False))
        return code
    except (ValueError, OSError) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
