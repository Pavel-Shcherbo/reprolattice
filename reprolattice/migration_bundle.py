"""Bounded migration evidence inventories and fresh offline SQL replay."""

import hashlib
from pathlib import Path
import re
import tempfile

from .jsonutil import strict_json
from .migration_model import compile_migrations
from .migration_state import read_app_snapshot, verify_migration_snapshot
from .sqlite_seed import canonical, identity

MAX_BUNDLE = 80 * 1024 * 1024
FILES = {
    "plan.json": 4 * 1024 * 1024,
    "report.json": 8 * 1024 * 1024,
    "baseline.sqlite": 16 * 1024 * 1024,
    "working.sqlite": 16 * 1024 * 1024,
}


def inventory(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("migration bundle requires an ordinary directory")
    result = {}
    for item in root.iterdir():
        if item.name == "manifest.json":
            continue
        if item.is_symlink():
            raise ValueError("migration bundle symlinks are unsupported")
        if item.name == "snapshots" and item.is_dir():
            files = list(item.iterdir())
            if len(files) > 64:
                raise ValueError("too many retained migration snapshots")
            for file in files:
                if (
                    not re.fullmatch("[0-9a-f]{64}\\.json", file.name)
                    or file.is_symlink()
                    or not file.is_file()
                ):
                    raise ValueError("invalid retained snapshot inventory")
                result["snapshots/" + file.name] = file
        elif item.name in FILES and item.is_file():
            result[item.name] = item
        else:
            raise ValueError("unexpected migration bundle file or directory")
    if not set(FILES) <= set(result) or "snapshots" not in {
        item.name for item in root.iterdir()
    }:
        raise ValueError("migration bundle is missing required evidence")
    total = 0
    for name, path in result.items():
        size = path.stat().st_size
        total += size
        if size > (16 * 1024 * 1024 if name.startswith("snapshots/") else FILES[name]):
            raise ValueError("migration evidence file exceeds its byte limit")
    if total > MAX_BUNDLE:
        raise ValueError("migration evidence exceeds 80 MiB")
    return result


def write_manifest(root):
    root = Path(root)
    files = inventory(root)
    manifest = {
        "format": "reprolattice.migration-bundle.v1",
        "files": {
            name: {
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for name, path in sorted(files.items())
        },
    }
    manifest["sha256"] = identity(manifest)
    with (root / "manifest.json").open("xb") as stream:
        stream.write(canonical(manifest) + b"\n")
    return manifest


def semantic_report(report):
    # Wall time and invocation IDs are observations; plan, SQL outcomes and logical states must match.
    return {
        key: value
        for key, value in report.items()
        if key not in ("run_id", "duration_seconds", "environment")
    }


def verify_migration_bundle(root):
    root = Path(root)
    files = inventory(root)
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("migration manifest cannot be a symlink")
    with manifest_path.open("rb") as stream:
        manifest = strict_json(stream.read(65537), max_bytes=65536)
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {"format", "files", "sha256"}
        or manifest["format"] != "reprolattice.migration-bundle.v1"
        or manifest["sha256"]
        != identity({key: value for key, value in manifest.items() if key != "sha256"})
    ):
        raise ValueError("invalid migration evidence manifest")
    if set(manifest["files"]) != set(files):
        raise ValueError("migration evidence inventory mismatch")
    for name, path in files.items():
        if manifest["files"][name] != {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }:
            raise ValueError("migration evidence file hash mismatch")
    plan = compile_migrations(
        strict_json(
            files["plan.json"].read_bytes(), max_bytes=4 * 1024 * 1024, max_nodes=250000
        )
    )
    report = strict_json(
        files["report.json"].read_bytes(), max_bytes=8 * 1024 * 1024, max_nodes=1000000
    )
    from .migration_runner import FORMAT, qualify_migrations

    if (
        not isinstance(report, dict)
        or report.get("format") != FORMAT
        or report.get("plan_sha256") != plan.sha256
    ):
        raise ValueError("migration report identity mismatch")
    retained = {}
    for name, path in files.items():
        if name.startswith("snapshots/"):
            snapshot = verify_migration_snapshot(
                strict_json(
                    path.read_bytes(), max_bytes=16 * 1024 * 1024, max_nodes=1000000
                )
            )
            if name != "snapshots/" + snapshot["sha256"] + ".json":
                raise ValueError("migration snapshot content identity mismatch")
            retained[snapshot["sha256"]] = snapshot
    baseline = read_app_snapshot(files["baseline.sqlite"])
    if (
        baseline["sha256"] != report.get("source_snapshot")
        or baseline["sha256"] not in retained
    ):
        raise ValueError("baseline database differs from retained source snapshot")
    from .migration_engine import MigrationDatabase

    class ExistingSnapshots:
        def put(self, value):
            if value["sha256"] not in retained or retained[value["sha256"]] != value:
                raise ValueError("working database snapshot was not retained")

    final = MigrationDatabase(
        files["working.sqlite"], plan, ExistingSnapshots()
    ).inspect()
    if final != report.get("final_state"):
        raise ValueError("working database or atomic history differs from the report")
    if report.get("status") == "cancelled":
        return {
            "passed": False,
            "content_files_checked": True,
            "replay_complete": False,
            "qualification_passed": False,
            "reason": "Cancelled invocation does not prove a full SQL replay",
            "plan_sha256": plan.sha256,
        }
    with tempfile.TemporaryDirectory(prefix="migration-replay-") as directory:
        replay = qualify_migrations(
            plan.definition, Path(directory) / "replay", source=files["baseline.sqlite"]
        )
    if semantic_report(replay) != semantic_report(report):
        raise ValueError(
            "fresh migration SQL replay differs from retained outcomes or logical states"
        )
    referenced = {report["source_snapshot"], report["final_state"]["snapshot"]}
    for phase in report["phases"]:
        referenced.update(
            phase[key]
            for key in ("before", "candidate", "after")
            if phase.get(key) is not None
        )
    if referenced != set(retained):
        raise ValueError(
            "migration bundle contains missing or unused snapshot evidence"
        )
    return {
        "passed": True,
        "replay_complete": True,
        "qualification_passed": report["qualification_passed"],
        "status": report["status"],
        "plan_sha256": plan.sha256,
        "snapshot_count": len(retained),
        "source_authenticated": False,
        "scope": "Fresh local SQL/content replay; no production deployment or authenticated provenance",
    }
