"""Execute a trusted local scenario suite and retain reviewable CI reports."""

import argparse
import json
import signal
import threading
from pathlib import Path

from .jsonutil import strict_json
from .reports import write_reports
from .suite_config import compile_suite, read_bounded
from .suite_runner import run_suite
from .queues import write_evidence


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run a local scenario suite with isolated cases"
    )
    parser.add_argument("spec", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New report directory; existing destinations are preserved",
    )
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument(
        "--queue-evidence",
        type=Path,
        help="New directory retaining complete per-case queue replay evidence",
    )
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--include-tag", action="append", default=[])
    parser.add_argument("--exclude-tag", action="append", default=[])
    args = parser.parse_args(argv)
    cancelled = threading.Event()
    previous = signal.getsignal(signal.SIGINT)
    try:
        definition = strict_json(
            read_bounded(args.spec, 2 * 1024 * 1024), max_bytes=2 * 1024 * 1024
        )
        plan = compile_suite(definition, args.root or args.spec.resolve().parent)
        if args.output.exists():
            raise ValueError("report destination already exists")
        if args.queue_evidence is not None:
            args.queue_evidence.mkdir(mode=0o700, parents=True, exist_ok=False)
        signal.signal(signal.SIGINT, lambda *_: cancelled.set())
        report = run_suite(
            plan,
            jobs=args.jobs,
            fail_fast=args.fail_fast,
            include_tags=args.include_tag,
            exclude_tags=args.exclude_tag,
            should_cancel=cancelled.is_set,
            on_queue=(
                (
                    lambda case, value: write_evidence(
                        value, args.queue_evidence / (case.id + ".json")
                    )
                )
                if args.queue_evidence is not None
                else None
            ),
        )
        manifest = write_reports(report, args.output)
        print(
            json.dumps(
                {
                    "run_id": report["run_id"],
                    "passed": report["passed"],
                    "counts": report["counts"],
                    "full_suite": report["full_suite"],
                    "reports": str(args.output),
                    "manifest": manifest,
                },
                indent=2,
            )
        )
        return 130 if cancelled.is_set() else 0 if report["passed"] else 1
    except (ValueError, OSError) as error:
        parser.exit(2, f"{error}\n")
    finally:
        signal.signal(signal.SIGINT, previous)


if __name__ == "__main__":
    raise SystemExit(main())
