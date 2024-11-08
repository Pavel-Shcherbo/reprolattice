"""Phase-bound typed snapshot inspection and bounded portable rehearsal envelopes."""

import base64
import copy
import hashlib
from pathlib import Path
import re
import tempfile

from .jsonutil import strict_json
from .migration_bundle import inventory, verify_migration_bundle, FILES
from .migration_state import verify_migration_snapshot
from .sqlite_seed import canonical, identity
from .state_diff import table_page, compare_rows

MAX_EXPORT = 12 * 1024 * 1024


def inspect_rehearsal(archive, project, record):
    value = archive.get(project, record)
    if value["report"] is None:
        return value
    value["snapshots"] = {}
    references = {
        value["report"]["source_snapshot"],
        value["report"]["final_state"]["snapshot"],
    }
    for phase in value["report"]["phases"]:
        references.update(
            phase[k] for k in ("before", "candidate", "after") if phase[k] is not None
        )
    for sha in sorted(references):
        snapshot = read_snapshot(archive, record, sha)
        value["snapshots"][sha] = {
            "sha256": sha,
            "schema": snapshot["schema"],
            "foreign_key_errors": snapshot["foreign_key_errors"],
            "tables": {
                name: {"columns": table["columns"], "row_count": len(table["rows"])}
                for name, table in snapshot["tables"].items()
            },
        }
    return value


def read_snapshot(archive, record, sha):
    path = archive.bundle(record) / "snapshots" / (sha + ".json")
    return verify_migration_snapshot(
        strict_json(path.read_bytes(), max_bytes=16 * 1024 * 1024, max_nodes=1000000)
    )


def portable(snapshot):
    value = copy.deepcopy(snapshot)
    value.pop("foreign_key_errors")
    value["format"] = "reprolattice.sqlite-snapshot.v1"
    value["sha256"] = identity({k: v for k, v in value.items() if k != "sha256"})
    return value


def phase_table(
    archive, project, record, phase, table, *, side="candidate", view="rows", offset=0
):
    value = archive.get(project, record)
    if value["report"] is None:
        raise ValueError("migration rehearsal has no completed evidence")
    if (
        type(phase) is not int
        or not 0 <= phase < len(value["report"]["phases"])
        or side not in ("before", "candidate", "after")
        or view not in ("rows", "diff")
    ):
        raise ValueError("unknown migration phase/side/view")
    item = value["report"]["phases"][phase]
    sha = item[side]
    if sha is None:
        raise ValueError("this phase has no retained " + side + " snapshot")
    selected = read_snapshot(archive, record, sha)
    before = read_snapshot(archive, record, item["before"])
    page = (
        table_page(portable(selected), table, offset=offset)
        if view == "rows"
        else compare_rows(
            portable(before),
            portable(selected),
            table,
            offset=offset,
            limit=25,
            status="changed",
        )
    )
    return {
        "record": record,
        "phase": phase,
        "side": side,
        "view": view,
        "source_snapshot_sha256": sha,
        "before_snapshot_sha256": item["before"],
        "page": page,
    }


def export_rehearsal(archive, project, record):
    value = archive.get(project, record)
    if value["report"] is None:
        raise ValueError("migration rehearsal has no completed evidence")
    root = archive.bundle(record)
    paths = inventory(root)
    paths["manifest.json"] = root / "manifest.json"
    if sum(path.stat().st_size for path in paths.values()) > 8 * 1024 * 1024:
        raise ValueError(
            "portable migration export exceeds 8 MiB raw data; use the local bundle directory"
        )
    document = {
        "format": "reprolattice.retained-migration.v1",
        "record": value["record"],
        "files": {
            name: base64.b64encode(path.read_bytes()).decode()
            for name, path in sorted(paths.items())
        },
    }
    document["sha256"] = identity(document)
    if len(canonical(document)) > MAX_EXPORT:
        raise ValueError("portable migration envelope exceeds 12 MiB")
    return document


def verify_retained_migration(document):
    if (
        not isinstance(document, dict)
        or set(document) != {"format", "record", "files", "sha256"}
        or document["format"] != "reprolattice.retained-migration.v1"
        or len(canonical(document)) > MAX_EXPORT
        or document["sha256"]
        != identity({k: v for k, v in document.items() if k != "sha256"})
    ):
        raise ValueError("retained migration envelope identity/format mismatch")
    files = document["files"]
    if (
        not isinstance(files, dict)
        or not 5 <= len(files) <= 69
        or not set(FILES) | {"manifest.json"} <= set(files)
    ):
        raise ValueError("retained migration envelope is missing bundle files")
    total = 0
    with tempfile.TemporaryDirectory(prefix="retained-migration-verify-") as temporary:
        root = Path(temporary)
        (root / "snapshots").mkdir()
        for name, encoded in files.items():
            if name not in set(FILES) | {"manifest.json"} and not re.fullmatch(
                r"snapshots/[0-9a-f]{64}\.json", name
            ):
                raise ValueError("invalid retained migration file path")
            if not isinstance(encoded, str) or len(encoded) > 12 * 1024 * 1024:
                raise ValueError("invalid retained migration file encoding")
            try:
                raw = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError) as error:
                raise ValueError("invalid retained migration file encoding") from error
            total += len(raw)
            if total > 8 * 1024 * 1024:
                raise ValueError("retained migration envelope raw data exceeds 8 MiB")
            (root / name).write_bytes(raw)
        manifest_sha = hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()
        record = document["record"]
        if (
            not isinstance(record, dict)
            or record.get("status") != "completed"
            or record.get("manifest_sha256") != manifest_sha
        ):
            raise ValueError("retained migration receipt is not bound to its bundle")
        proof = verify_migration_bundle(root)
    return {**proof, "record": record["id"], "receipt_binding_verified": True}
