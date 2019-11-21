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


def bounded_number(value):
    if not number(value):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def json_equal(left, right):
    if number(left) and number(right):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            json_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            json_equal(a, b) for a, b in zip(left, right)
        )
    return left == right


def pointer_tokens(pointer):
    if (
        not isinstance(pointer, str)
        or len(pointer) > 1024
        or (pointer and not pointer.startswith("/"))
    ):
        raise ValueError(
            "assertion path must be a JSON pointer of at most 1024 characters"
        )
    if pointer == "":
        return ()
    parts = pointer[1:].split("/")
    if len(parts) > 50:
        raise ValueError("assertion path has too many components")
    result = []
    for part in parts:
        for index, character in enumerate(part):
            if character == "~" and (
                index + 1 == len(part) or part[index + 1] not in "01"
            ):
                raise ValueError("JSON pointer escapes must use ~0 or ~1")
        result.append(part.replace("~1", "/").replace("~0", "~"))
    return tuple(result)


