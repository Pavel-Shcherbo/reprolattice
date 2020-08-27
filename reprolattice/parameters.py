"""Bounded JSON parameter expansion without evaluation or shell interpolation."""

import copy
import hashlib
import itertools
import json
import re

from .jsonutil import validate_json
from .redaction import redact

NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,47}$")
TOKEN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]{0,47})\}")


def parameter_name(value):
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise ValueError("parameter names must be bounded ASCII identifiers")
    return value


def variants(matrix):
    if not isinstance(matrix, dict) or len(matrix) > 6:
        raise ValueError("matrix must be an object of at most six dimensions")
    for key in matrix:
        parameter_name(key)
    keys = sorted(matrix)
    count = 1
    for key in keys:
        parameter_name(key)
        if key in {"python", "case_id"}:
            raise ValueError("matrix cannot replace a reserved runtime parameter")
        values = matrix[key]
        if not isinstance(values, list) or not 1 <= len(values) <= 16:
            raise ValueError("matrix dimensions require 1–16 values")
        validate_json(values, max_bytes=65536, max_depth=20, max_nodes=5000)
        count *= len(values)
        if count > 64:
            raise ValueError("case matrix exceeds 64 combinations")
        identities = [
            json.dumps(value, sort_keys=True, separators=(",", ":")) for value in values
        ]
        if len(set(identities)) != len(identities):
            raise ValueError("matrix dimension contains duplicate typed values")
    combinations = itertools.product(*(matrix[key] for key in keys))
    return [dict(zip(keys, copy.deepcopy(values))) for values in combinations]


