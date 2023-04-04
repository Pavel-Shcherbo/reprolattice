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


def primary_key(table):
    if not table:
        return []
    columns = table["columns"]
    indexes = []
    for column in columns:
        value = column["primary_key"]
        if type(value) is not int or not 0 <= value <= len(columns):
            return []
        if value:
            indexes.append((value, column["name"]))
    indexes.sort()
    if [index for index, _ in indexes] != list(range(1, len(indexes) + 1)):
        return []
    keys = [name for _, name in indexes]
    seen = set()
    if not keys:
        return []
    for row in table["rows"]:
        if any(row[name]["type"] == "null" for name in keys):
            return []
        encoded = canonical({name: row[name] for name in keys})
        if encoded in seen:
            return []
        seen.add(encoded)
    return keys


def compare_rows(before, after, table, *, offset=0, limit=25, status="changed"):
    verify_database_snapshot(before)
    verify_database_snapshot(after)
    if not isinstance(table, str) or table not in set(before["tables"]) | set(
        after["tables"]
    ):
        raise ValueError("unknown retained table")
    if status not in ("changed", "all", "added", "removed", "modified", "unchanged"):
        raise ValueError("unknown row change filter")
    left, right = before["tables"].get(table), after["tables"].get(table)
    keys = primary_key(left)
    if (
        not keys
        or keys != primary_key(right)
        or [col["name"] for col in left["columns"]]
        != [col["name"] for col in right["columns"]]
    ):
        keys = []
    rows = []
    if keys:

        def keyed(data):
            return {
                canonical({name: row[name] for name in keys}): row
                for row in data["rows"]
            }

        a, b = keyed(left), keyed(right)
        for key in sorted(set(a) | set(b)):
            old, new = a.get(key), b.get(key)
            kind = (
                "added"
                if old is None
                else (
                    "removed"
                    if new is None
                    else "unchanged" if canonical(old) == canonical(new) else "modified"
                )
            )
            source = old if old is not None else new
            rows.append(
                {
                    "change": kind,
                    "key": {name: source[name] for name in keys},
                    "count": 1,
                    "before": old,
                    "after": new,
                }
            )
    else:

        def counted(data):
            values = (
                {} if data is None else {canonical(row): row for row in data["rows"]}
            )
            counts = (
                Counter()
                if data is None
                else Counter(canonical(row) for row in data["rows"])
            )
            return values, counts

        a, ac = counted(left)
        b, bc = counted(right)
        for encoded in sorted(set(a) | set(b)):
            common = min(ac[encoded], bc[encoded])
            for kind, count, old, new in (
                ("unchanged", common, a.get(encoded), b.get(encoded)),
                ("removed", ac[encoded] - common, a.get(encoded), None),
                ("added", bc[encoded] - common, None, b.get(encoded)),
            ):
                if count:
                    rows.append(
                        {
                            "change": kind,
                            "key": None,
                            "count": count,
                            "before": old,
                            "after": new,
                        }
                    )
    counts = {
        kind: sum(row["count"] for row in rows if row["change"] == kind)
        for kind in ("added", "removed", "modified", "unchanged")
    }
    selected = [
        row
        for row in rows
        if status == "all"
        or status == "changed"
        and row["change"] != "unchanged"
        or row["change"] == status
    ]
    return {
        "table": table,
        "before_sha256": before["sha256"],
        "after_sha256": after["sha256"],
        "identity_mode": "declared_primary_key" if keys else "row_multiset",
        "primary_key": keys,
        "schema_changed": left is None
        or right is None
        or left["columns"] != right["columns"],
        "counts": counts,
        "filter": status,
        **bounded_page(selected, offset, limit),
    }
