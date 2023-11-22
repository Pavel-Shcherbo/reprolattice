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


