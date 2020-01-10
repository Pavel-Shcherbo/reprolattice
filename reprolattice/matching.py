"""Bounded request matching for ordered HTTP scenarios."""

import copy
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from .assertions import compile_rules, json_equal
from .jsonutil import validate_json

METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


def glob_match(pattern, value):
    """Match * and ? with bounded greedy scanning, without user regular expressions."""
    if len(pattern) > 256 or len(value) > 8192:
        return False
    left = right = 0
    star = -1
    checkpoint = 0
    while right < len(value):
        if left < len(pattern) and (
            pattern[left] == "?" or pattern[left] == value[right]
        ):
            left += 1
            right += 1
        elif left < len(pattern) and pattern[left] == "*":
            star = left
            checkpoint = right
            left += 1
        elif star >= 0:
            checkpoint += 1
            right = checkpoint
            left = star + 1
        else:
            return False
    while left < len(pattern) and pattern[left] == "*":
        left += 1
    return left == len(pattern)


def canonical_headers(headers):
    grouped = {}
    pairs = headers.items() if isinstance(headers, dict) else headers
    for key, value in pairs:
        normalized = key.casefold()
        grouped.setdefault(normalized, []).append(value)
    return {
        key: values[0] if len(values) == 1 else values
        for key, values in grouped.items()
    }


