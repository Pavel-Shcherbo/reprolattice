"""Explicit JSON-pointer assertions without expressions or executable code."""

import copy
import json
import math
from dataclasses import dataclass
from decimal import Decimal, localcontext

from .jsonutil import validate_json
from .redaction import redact, secret_key

MISSING = object()
OPERATIONS = frozenset(
    {
        "equals",
        "not_equals",
        "exists",
        "absent",
        "type",
        "contains",
        "subset",
        "one_of",
        "approx",
        "gt",
        "gte",
        "lt",
        "lte",
    }
)
JSON_TYPES = frozenset(
    {"null", "boolean", "number", "integer", "string", "array", "object"}
)


def number(value):
    return type(value) is int or (type(value) is float and math.isfinite(value))


