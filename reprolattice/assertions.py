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


def resolve(value, tokens):
    current = value
    for token in tokens:
        if isinstance(current, dict):
            current = current.get(token, MISSING)
        elif isinstance(current, list):
            if (
                not token
                or len(token) > 10
                or any(character not in "0123456789" for character in token)
                or (len(token) > 1 and token[0] == "0")
            ):
                return MISSING
            index = int(token)
            current = current[index] if index < len(current) else MISSING
        else:
            return MISSING
        if current is MISSING:
            return MISSING
    return current


def type_matches(value, expected):
    return {
        "null": value is None,
        "boolean": type(value) is bool,
        "number": number(value),
        "integer": type(value) is int
        or (type(value) is float and math.isfinite(value) and value.is_integer()),
        "string": isinstance(value, str),
        "array": isinstance(value, list),
        "object": isinstance(value, dict),
    }[expected]


def subset(actual, expected):
    if not isinstance(actual, dict):
        return False
    for key, value in expected.items():
        if key not in actual:
            return False
        if isinstance(value, dict):
            if not subset(actual[key], value):
                return False
        elif not json_equal(actual[key], value):
            return False
    return True


def visible(value, tokens):
    if value is MISSING:
        return {"missing": True}
    cleaned = (
        "[REDACTED]" if any(secret_key(token) for token in tokens) else redact(value)
    )
    if len(json.dumps(cleaned, allow_nan=False)) > 4096:
        return {"summary": "value omitted from report because it exceeds 4 KiB"}
    return cleaned


@dataclass(frozen=True)
class Rule:
    id: str
    path: str
    tokens: tuple
    operation: str
    operand: object = None
    atol: float = 0.0
    rtol: float = 0.0

    def evaluate(self, value):
        actual = resolve(value, self.tokens)
        operation = self.operation
        if operation == "exists":
            passed = actual is not MISSING
        elif operation == "absent":
            passed = actual is MISSING
        elif actual is MISSING:
            passed = False
        elif operation == "equals":
            passed = json_equal(actual, self.operand)
        elif operation == "not_equals":
            passed = not json_equal(actual, self.operand)
        elif operation == "type":
            passed = type_matches(actual, self.operand)
        elif operation == "contains":
            passed = (
                self.operand in actual
                if isinstance(actual, str) and isinstance(self.operand, str)
                else (
                    any(json_equal(item, self.operand) for item in actual)
                    if isinstance(actual, list)
                    else False
                )
            )
        elif operation == "subset":
            passed = subset(actual, self.operand)
        elif operation == "one_of":
            passed = any(json_equal(actual, option) for option in self.operand)
        elif operation == "approx":
            passed = False
            if bounded_number(actual):
                with localcontext() as context:
                    context.prec = 1400
                    observed, expected = Decimal(str(actual)), Decimal(
                        str(self.operand)
                    )
                    tolerance = Decimal(str(self.atol)) + Decimal(str(self.rtol)) * abs(
                        expected
                    )
                    passed = abs(observed - expected) <= tolerance
        elif not number(actual):
            passed = False
        elif operation == "gt":
            passed = actual > self.operand
        elif operation == "gte":
            passed = actual >= self.operand
        elif operation == "lt":
            passed = actual < self.operand
        else:
            passed = actual <= self.operand
        result = {
            "id": self.id,
            "path": self.path,
            "op": operation,
            "passed": bool(passed),
            "actual": visible(actual, self.tokens),
        }
        if operation not in {"exists", "absent"}:
            result["expected"] = visible(self.operand, self.tokens)
        if operation == "approx":
            result.update({"atol": self.atol, "rtol": self.rtol})
        if not passed:
            result["reason"] = "missing" if actual is MISSING else "condition_not_met"
        return result


