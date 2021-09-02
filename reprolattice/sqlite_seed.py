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


def sqlite_value(value):
    if isinstance(value, dict) and set(value) == {"$blob"}:
        encoded = value["$blob"]
        if (
            not isinstance(encoded, str)
            or len(encoded) > 131072
            or not re.fullmatch(r"(?:[0-9a-f]{2})*", encoded)
        ):
            raise ValueError(
                "BLOB values require bounded lowercase even-length hexadecimal"
            )
        return bytes.fromhex(encoded)
    if value is None or type(value) in {str, int, float}:
        if type(value) is int and not -(2**63) <= value < 2**63:
            raise ValueError("SQLite integer exceeds signed 64-bit range")
        if type(value) is float and not math.isfinite(value):
            raise ValueError("SQLite real must be finite")
        if isinstance(value, str) and len(value.encode()) > 65536:
            raise ValueError("SQLite text exceeds 64 KiB")
        return value
    raise ValueError(
        "SQLite values require null, integer, real, text or an explicit BLOB"
    )


def typed(value):
    if value is None:
        return {"type": "null", "value": None}
    if type(value) is int:
        return {"type": "integer", "value": value}
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("non-finite SQLite result")
        return {"type": "real", "value": value}
    if isinstance(value, str):
        if len(value.encode()) > 65536:
            raise ValueError("SQLite result text exceeds 64 KiB")
        return {"type": "text", "value": value}
    if isinstance(value, bytes):
        if len(value) > 65536:
            raise ValueError("SQLite result BLOB exceeds 64 KiB")
        return {"type": "blob", "value": value.hex()}
    raise ValueError("unsupported SQLite storage value")


