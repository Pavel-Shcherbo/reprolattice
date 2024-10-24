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


