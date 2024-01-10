"""Rehearse ordered up/repeat/down cycles from an untouched copied baseline."""

from pathlib import Path
import platform
import sqlite3
import time
import uuid

from .migration_engine import MigrationDatabase
from .migration_model import compile_migrations, compact_checks
from .migration_state import SnapshotFiles, clone_database, read_app_snapshot
from .sqlite_inspect import check_queries
from .sqlite_seed import canonical, create_database

FORMAT = "reprolattice.migration-report.v1"


def qualify_migrations(
    definition, destination, *, seed=None, source=None, should_cancel=None
):
    if (seed is None) == (source is None):
        raise ValueError("choose one structured seed or existing source database")
    if should_cancel is not None and not callable(should_cancel):
        raise ValueError("migration cancellation must be callable")
    plan = compile_migrations(definition)
    destination = Path(destination)
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    snapshots = SnapshotFiles(destination / "snapshots")
    (destination / "plan.json").write_bytes(canonical(plan.definition) + b"\n")
    baseline = destination / "baseline.sqlite"
    working = destination / "working.sqlite"
    started = time.monotonic()
    if seed is not None:
        create_database(seed, baseline)
        initial = read_app_snapshot(baseline)
        if any(
            item["name"].casefold().startswith("_reprolattice_")
            for item in initial["schema"]
        ):
            raise ValueError("seed uses reserved migration metadata names")
    else:
        initial = clone_database(source, baseline, should_cancel=should_cancel)
    user_tables = [name for name in initial["tables"] if not name.startswith("sqlite_")]
    if len(user_tables) > 62 or len(initial["schema"]) > 254:
        raise ValueError(
            "migration rehearsal reserves room for two protected metadata tables"
        )
    snapshots.put(initial)
    copied = clone_database(baseline, working, should_cancel=should_cancel)
    if copied["sha256"] != initial["sha256"]:
        raise ValueError("working copy differs from baseline snapshot")
    engine = MigrationDatabase(working, plan, snapshots, initialize=True)
    preconditions = compact_checks(
        check_queries(baseline, plan.definition["baseline_checks"])
    )
    report = {
        "format": FORMAT,
        "run_id": str(uuid.uuid4()),
        "plan_sha256": plan.sha256,
        "source_snapshot": initial["sha256"],
        "baseline_checks": preconditions,
        "environment": {
            "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version,
        },
        "phases": [],
        "status": "failed",
        "qualification_passed": False,
        "restored_exactly": False,
        "final_state": None,
        "duration_seconds": None,
        "snapshot_bytes": 0,
    }
    if preconditions["passed"]:
        failed = False
        for index in range(len(plan.definition["migrations"])):
            result = engine.step(index, "up", should_cancel=should_cancel)
            report["phases"].append(result)
            if result["status"] != "applied":
                failed = True
                break
            repeated = engine.step(index, "up", should_cancel=should_cancel)
            report["phases"].append(repeated)
            if (
                repeated["status"] != "already_applied"
                or repeated["after"] != result["after"]
            ):
                failed = True
                break
        if not failed:
            for index in reversed(range(len(plan.definition["migrations"]))):
                result = engine.step(index, "down", should_cancel=should_cancel)
                report["phases"].append(result)
                if result["status"] != "reverted":
                    failed = True
                    break
                repeated = engine.step(index, "down", should_cancel=should_cancel)
                report["phases"].append(repeated)
                if (
                    repeated["status"] != "already_absent"
                    or repeated["after"] != result["after"]
                ):
                    failed = True
                    break
        if any(item["status"] == "cancelled" for item in report["phases"]):
            report["status"] = "cancelled"
        elif not failed:
            report["status"] = "passed"
    final = engine.inspect()
    report["final_state"] = final
    report["restored_exactly"] = (
        final["snapshot"] == initial["sha256"] and not final["stack"]
    )
    report["qualification_passed"] = (
        report["status"] == "passed" and report["restored_exactly"]
    )
    report["duration_seconds"] = time.monotonic() - started
    report["snapshot_bytes"] = snapshots.bytes
    # Close every SQLite connection before retaining the on-disk evidence set.
    (destination / "report.json").write_bytes(canonical(report) + b"\n")
    from .migration_bundle import write_manifest

    write_manifest(destination)
    return report
