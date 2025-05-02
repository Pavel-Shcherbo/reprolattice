"""A real crashed delivery followed by an idempotent or deliberately faulty retry."""

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def command(operation, **fields):
    payload = json.dumps({"operation": operation, **fields}).encode()
    request = Request(
        os.environ["REPROLATTICE_QUEUE_URL"],
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Queue-Fixture": os.environ["REPROLATTICE_QUEUE_CAPABILITY"],
        },
    )
    try:
        with urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        try:
            return error.code, json.loads(error.read())
        finally:
            error.close()


def request(operation, **fields):
    code, value = command(operation, **fields)
    if code != 200:
        raise RuntimeError(value)
    return value


def initialize():
    with closing(sqlite3.connect("queue-effects.sqlite")) as db, db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS inventory(part TEXT PRIMARY KEY,available INTEGER NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS processed(job TEXT PRIMARY KEY,units INTEGER NOT NULL)"
        )
        db.execute("INSERT OR IGNORE INTO inventory VALUES('part-42',10)")


def apply_effect(message, duplicate):
    with closing(sqlite3.connect("queue-effects.sqlite")) as db, db:
        known = db.execute(
            "SELECT units FROM processed WHERE job=?", (message["id"],)
        ).fetchone()
        if known is None or duplicate:
            db.execute(
                "UPDATE inventory SET available=available-? WHERE part='part-42'",
                (message["body"]["units"],),
            )
            db.execute(
                "INSERT OR IGNORE INTO processed VALUES(?,?)",
                (message["id"], message["body"]["units"]),
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--behavior", choices=("idempotent", "duplicate"), default="idempotent"
    )
    parser.add_argument("--first-delivery", action="store_true")
    args = parser.parse_args()
    initialize()
    if args.first_delivery:
        message = request("receive", owner="crashed-worker")["message"]
        apply_effect(message, False)
        Path("unacknowledged-delivery.json").write_text(json.dumps(message))
        os._exit(17)
    crashed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--first-delivery"], timeout=5
    )
    if crashed.returncode != 17:
        raise RuntimeError(
            "first delivery did not stop after its committed side effect"
        )
    stale = json.loads(Path("unacknowledged-delivery.json").read_text())
    request("advance", seconds=5)
    retry = request("receive", owner="retry-worker")["message"]
    if retry["id"] != stale["id"] or retry["attempt"] != 2:
        raise RuntimeError("the unacknowledged message was not redelivered")
    stale_status, _ = command("ack", owner="crashed-worker", delivery=stale["delivery"])
    apply_effect(retry, args.behavior == "duplicate")
    request("ack", owner="retry-worker", delivery=retry["delivery"])
    repeated_ack = request("ack", owner="retry-worker", delivery=retry["delivery"])
    if not repeated_ack["reused"]:
        raise RuntimeError("acknowledgement response was not recoverable")
    request("publish", id="poison-1", body={"kind": "poison"}, request_key="poison")
    for _ in range(2):
        poison = request("receive", owner="poison-worker")["message"]
        request("nack", owner="poison-worker", delivery=poison["delivery"])
    publication = {"id": "audit-1", "body": {"kind": "audit"}, "request_key": "audit"}
    request("publish", **publication)
    repeated = request("publish", **publication)
    audit = request("receive", owner="audit-worker")["message"]
    request("ack", owner="audit-worker", delivery=audit["delivery"])
    if request("receive", owner="audit-worker")["message"] is not None:
        raise RuntimeError("unexpected ready queue message")
    status = request("status")
    with closing(sqlite3.connect("queue-effects.sqlite")) as db:
        processed = db.execute("SELECT count(*) FROM processed").fetchone()[0]
    print(
        json.dumps(
            {
                "processed": processed,
                "stale_ack_rejected": stale_status == 400,
                "dead_letters": status["counts"]["dead"],
                "duplicate_publish_reused": repeated["reused"],
            }
        )
    )


if __name__ == "__main__":
    main()
