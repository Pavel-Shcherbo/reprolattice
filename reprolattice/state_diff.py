"""Typed key-aware row differences with duplicate-preserving fallback and paging."""

from collections import Counter
import copy

from .sqlite_inspect import verify_database_snapshot
from .sqlite_seed import canonical, identity


def page_limits(offset, limit):
    if (
        type(offset) is not int
        or not 0 <= offset <= 40000
        or type(limit) is not int
        or not 1 <= limit <= 100
    ):
        raise ValueError("state pages require offset 0–40,000 and limit 1–100")


def bounded_page(items, offset, limit):
    page_limits(offset, limit)
    if offset > len(items):
        raise ValueError("state page offset exceeds result length")
    output, size = [], 0
    for item in items[offset : offset + limit]:
        encoded = len(canonical(item))
        if encoded > 1024 * 1024:
            raise ValueError(
                "one state row exceeds the 1 MiB display budget; export full evidence"
            )
        if output and size + encoded > 1024 * 1024:
            break
        output.append(copy.deepcopy(item))
        size += encoded
    next_offset = offset + len(output)
    return {
        "items": output,
        "offset": offset,
        "total": len(items),
        "next_offset": next_offset if next_offset < len(items) else None,
    }


def table_page(snapshot, table, *, offset=0, limit=25):
    verify_database_snapshot(snapshot)
    if not isinstance(table, str) or table not in snapshot["tables"]:
        raise ValueError("unknown retained table")
    data = snapshot["tables"][table]
    return {
        "snapshot_sha256": snapshot["sha256"],
        "table": table,
        "columns": copy.deepcopy(data["columns"]),
        **bounded_page(data["rows"], offset, limit),
    }


