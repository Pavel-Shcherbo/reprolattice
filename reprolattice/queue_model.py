"""Explicit local queue fixture limits and final-state assertion contracts."""

import copy
import hashlib
import json
import re

from .assertions import compile_rules
from .harness import application_contract
from .jsonutil import validate_json

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")
MAX_EVIDENCE = 8 * 1024 * 1024


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


