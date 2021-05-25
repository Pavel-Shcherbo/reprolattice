"""Retry a dependency and persist one inventory receipt in an existing database."""

import argparse
import http.client
import json
import os
import sqlite3
from contextlib import closing
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--omit-write", action="store_true")
    parser.add_argument("--database", default="inventory.sqlite")
    args = parser.parse_args()
    target = urlsplit(os.environ["REPROLATTICE_BASE_URL"])
    for _ in range(3):
        connection = http.client.HTTPConnection(target.hostname, target.port, timeout=2)
        try:
            connection.request("GET", "/inventory/part-42")
            response = connection.getresponse()
            payload = json.loads(response.read())
            if response.status == 200:
                available = payload["available"]
                if type(available) is not int or available < 0:
                    raise ValueError("invalid inventory quantity")
                if not args.omit_write:
                    with closing(sqlite3.connect(args.database)) as db, db:
                        db.execute("PRAGMA foreign_keys=ON")
                        changed = db.execute(
                            "UPDATE inventory SET available=? WHERE part=?",
                            (available, "part-42"),
                        )
                        if changed.rowcount != 1:
                            raise ValueError("inventory item is missing")
                        db.execute(
                            "INSERT INTO receipts(id,part,quantity) VALUES(1,?,?)",
                            ("part-42", available),
                        )
                print(json.dumps(payload))
                return 0
            if response.status not in {429, 502, 503, 504}:
                break
        finally:
            connection.close()
    print(json.dumps({"error": "inventory request failed"}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
