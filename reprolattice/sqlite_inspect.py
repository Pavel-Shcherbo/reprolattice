"""Bounded read-only SQLite checks and typed logical database snapshots."""

import copy
import math
import sqlite3
import time
from collections import Counter
from contextlib import contextmanager, closing, nullcontext
from pathlib import Path

from .jsonutil import validate_json
from .sqlite_seed import MAX_DATABASE, canonical, identity, quoted, sqlite_value, typed

FUNCTIONS = frozenset(
    "abs avg char coalesce count cume_dist dense_rank first_value format hex ifnull iif instr json_array json_array_length json_extract json_group_array json_group_object json_object json_type json_valid lag last_value lead length likelihood likely lower ltrim max min nth_value ntile nullif percent_rank printf quote rank replace round row_number rtrim sign substr substring sum total trim typeof unicode unlikely upper zeroblob".split()
)


class Budget:
    def __init__(self, timeout=2, should_cancel=None):
        if (
            type(timeout) not in (int, float)
            or not math.isfinite(timeout)
            or not 0 < timeout <= 10
        ):
            raise ValueError(
                "SQLite inspection timeout must be between 0 and 10 seconds"
            )
        if should_cancel is not None and not callable(should_cancel):
            raise ValueError("cancellation must be callable")
        self.deadline = time.monotonic() + timeout
        self.steps = 0
        self.cancelled = should_cancel
        self.reason = None

    def progress(self):
        self.steps += 1000
        if self.cancelled and self.cancelled():
            self.reason = "cancelled"
        elif time.monotonic() >= self.deadline:
            self.reason = "time budget exceeded"
        elif self.steps > 2_000_000:
            self.reason = "VM instruction budget exceeded"
        return int(self.reason is not None)

    def check(self):
        if self.cancelled and self.cancelled():
            self.reason = "cancelled"
        elif time.monotonic() >= self.deadline:
            self.reason = "time budget exceeded"
        if self.reason:
            raise ValueError("SQLite inspection " + self.reason)


def file_budget(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("SQLite input must be an ordinary existing file")
    total = 0
    for suffix, limit in [
        ("", MAX_DATABASE),
        ("-wal", MAX_DATABASE),
        ("-shm", 1024 * 1024),
        ("-journal", MAX_DATABASE),
    ]:
        item = Path(str(path) + suffix)
        if item.is_symlink():
            raise ValueError("SQLite sidecar symlinks are unsupported")
        if item.exists():
            if not item.is_file() or item.stat().st_size > limit:
                raise ValueError("SQLite file or sidecar exceeds its byte budget")
            total += item.stat().st_size
    return total


