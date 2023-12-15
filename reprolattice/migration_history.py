"""Protected, deterministic history committed with each isolated schema change."""

import json

from .migration_model import PREFIX
from .sqlite_seed import canonical, identity

STACK = PREFIX + "migration_stack"
EVENTS = PREFIX + "migration_events"


def initialize_history(db):
    if db.execute(
        "SELECT name FROM sqlite_schema WHERE lower(name) GLOB '_reprolattice_*'"
    ).fetchone():
        raise ValueError("migration source contains reserved rehearsal metadata")
    db.execute(
        "CREATE TABLE "
        + STACK
        + "(position INTEGER PRIMARY KEY,migration TEXT UNIQUE NOT NULL,step_sha256 TEXT NOT NULL,before_sha256 TEXT NOT NULL,after_sha256 TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE "
        + EVENTS
        + "(seq INTEGER PRIMARY KEY,kind TEXT NOT NULL,migration TEXT NOT NULL,payload BLOB NOT NULL,previous_sha256 TEXT NOT NULL,sha256 TEXT NOT NULL)"
    )


def history(db, plan):
    names = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_schema WHERE lower(name) GLOB '_reprolattice_*'"
        )
    }
    if names != {STACK, EVENTS}:
        raise ValueError("reserved migration namespace or metadata schema was changed")
    stack = [
        dict(
            zip(
                (
                    "position",
                    "migration",
                    "step_sha256",
                    "before_sha256",
                    "after_sha256",
                ),
                row,
            )
        )
        for row in db.execute("SELECT * FROM " + STACK + " ORDER BY position")
    ]
    reconstructed = []
    previous = identity([])
    events = []
    for row in db.execute("SELECT * FROM " + EVENTS + " ORDER BY seq"):
        seq, kind, migration, raw, parent, digest = row
        payload = json.loads(raw)
        if (
            not isinstance(payload, dict)
            or set(payload)
            != {"position", "migration", "step_sha256", "before_sha256", "after_sha256"}
            or type(payload["position"]) is not int
            or not 1 <= payload["position"] <= len(plan.definition["migrations"])
        ):
            raise ValueError("invalid migration history payload")
        declared = plan.definition["migrations"][payload["position"] - 1]
        if (
            payload["migration"] != migration
            or migration != declared["id"]
            or payload["step_sha256"] != identity(declared)
        ):
            raise ValueError(
                "migration history differs from the supplied immutable plan"
            )

        if (
            seq != len(events) + 1
            or parent != previous
            or digest
            != identity(
                {
                    "seq": seq,
                    "kind": kind,
                    "migration": migration,
                    "payload": payload,
                    "previous_sha256": parent,
                }
            )
        ):
            raise ValueError("migration history chain is damaged")
        if kind == "up":
            reconstructed.append(payload)
        elif kind == "down":
            if not reconstructed or reconstructed[-1] != payload:
                raise ValueError("migration history has an out-of-order reversal")
            reconstructed.pop()
        else:
            raise ValueError("unknown migration history event")
        previous = digest
        events.append(
            {"seq": seq, "kind": kind, "migration": migration, "sha256": digest}
        )
    if reconstructed != stack:
        raise ValueError("migration stack differs from its atomic history")
    if len(stack) > len(plan.definition["migrations"]):
        raise ValueError("working database has unknown migration versions")
    for position, item in enumerate(stack):
        step = plan.definition["migrations"][position]
        if (
            item["position"] != position + 1
            or item["migration"] != step["id"]
            or item["step_sha256"] != identity(step)
        ):
            raise ValueError("applied migration differs from the supplied ordered plan")
    return stack, events, previous


def append_history(db, plan, kind, item):
    _, events, previous = history(db, plan)
    seq = len(events) + 1
    digest = identity(
        {
            "seq": seq,
            "kind": kind,
            "migration": item["migration"],
            "payload": item,
            "previous_sha256": previous,
        }
    )
    db.execute(
        "INSERT INTO " + EVENTS + " VALUES(?,?,?,?,?,?)",
        (seq, kind, item["migration"], canonical(item), previous, digest),
    )
