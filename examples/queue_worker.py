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


