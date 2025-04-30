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


