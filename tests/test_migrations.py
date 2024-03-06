"""Isolated migration outcomes, forensic failures and independent evidence replay."""

import copy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from reprolattice.migration_bundle import verify_migration_bundle, write_manifest
from reprolattice.migration_engine import MigrationDatabase
from reprolattice.migration_model import compile_migrations
from reprolattice.migration_runner import qualify_migrations
from reprolattice.migration_state import read_app_snapshot, SnapshotFiles, ROWID
from reprolattice.sqlite_seed import canonical, create_database

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def statement(sql, label="change", parameters=None):
    return {"id": label, "sql": sql, "parameters": parameters or []}


