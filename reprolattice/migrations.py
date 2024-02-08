"""Qualify reversible SQLite migrations on isolated copies and replay evidence."""

import argparse
import json
from pathlib import Path
import sqlite3

from .jsonutil import strict_json
from .migration_bundle import verify_migration_bundle
from .migration_runner import qualify_migrations


def load(path):
    with path.open("rb") as stream:
        return strict_json(
            stream.read(4 * 1024 * 1024 + 1),
            max_bytes=4 * 1024 * 1024,
            max_nodes=250000,
        )


