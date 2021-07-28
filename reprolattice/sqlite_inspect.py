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
    pass
