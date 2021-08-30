"""Structured, constrained SQLite fixtures published without overwriting files."""

import copy
import hashlib
import json
import math
import os
import re
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from .jsonutil import validate_json

NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
TYPES = {"INTEGER", "REAL", "TEXT", "BLOB"}
MAX_DATABASE = 16 * 1024 * 1024


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode()


def identity(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def name(value):
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise ValueError(
            "SQLite fixture identifiers require at most 64 ASCII letters, digits or underscores"
        )
    return value


def quoted(value):
    return '"' + value.replace('"', '""') + '"'


