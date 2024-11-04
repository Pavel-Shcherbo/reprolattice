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


