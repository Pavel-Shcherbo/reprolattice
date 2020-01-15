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


def assertion_issues(component, value, rules):
    issues = []
    for rule in rules:
        result = rule.evaluate(value)
        if not result["passed"]:
            issues.append(
                {
                    "component": component,
                    "id": rule.id,
                    "path": rule.path,
                    "reason": result["reason"],
                }
            )
    return issues


@dataclass(frozen=True)
class RequestMatcher:
    method: str
    path: str
    pattern: bool
    headers: dict
    has_json: bool
    json_value: object
    json_rules: tuple
    query_rules: tuple
    header_rules: tuple
    query_component: bool

    def match(self, method, path, body, headers):
        issues = []
        if method != self.method:
            issues.append({"component": "method", "reason": "method_mismatch"})
        if len(path) > 8192:
            return issues + [{"component": "path", "reason": "path_budget_exceeded"}]
        try:
            parsed = urlsplit(path)
        except ValueError:
            return issues + [{"component": "path", "reason": "invalid_path"}]
        if (
            parsed.scheme
            or parsed.netloc
            or parsed.fragment
            or not path.startswith("/")
            or path.startswith("//")
        ):
            return issues + [
                {"component": "path", "reason": "invalid_origin_relative_path"}
            ]
        candidate = parsed.path if self.pattern or self.query_component else path
        matched = (
            glob_match(self.path, candidate) if self.pattern else self.path == candidate
        )
        if not matched:
            issues.append({"component": "path", "reason": "path_mismatch"})
        actual_headers = canonical_headers(headers)
        for key, expected in self.headers.items():
            if actual_headers.get(key) != expected:
                issues.append(
                    {
                        "component": "headers",
                        "path": "/" + key,
                        "reason": "header_mismatch",
                    }
                )
        if self.has_json and not json_equal(body, self.json_value):
            issues.append({"component": "json", "path": "", "reason": "body_mismatch"})
        issues.extend(assertion_issues("json", body, self.json_rules))
        issues.extend(assertion_issues("headers", actual_headers, self.header_rules))
        if self.query_component:
            try:
                values = parse_qs(
                    parsed.query, keep_blank_values=True, max_num_fields=1000
                )
            except ValueError:
                issues.append({"component": "query", "reason": "query_budget_exceeded"})
            else:
                query = {
                    key: value[0] if len(value) == 1 else value
                    for key, value in values.items()
                }
                issues.extend(assertion_issues("query", query, self.query_rules))
        return issues


def compile_request(definition):
    allowed = {
        "method",
        "path",
        "path_pattern",
        "headers",
        "json",
        "json_assertions",
        "query_assertions",
        "header_assertions",
    }
    if not isinstance(definition, dict) or set(definition) - allowed:
        raise ValueError("request contains unsupported fields")
    method = definition.get("method")
    if not isinstance(method, str) or method not in METHODS:
        raise ValueError("unsupported request method")
    if ("path" in definition) == ("path_pattern" in definition):
        raise ValueError("request requires exactly one of path or path_pattern")
    pattern = "path_pattern" in definition
    path = definition.get("path_pattern") if pattern else definition.get("path")
    maximum = 256 if pattern else 8192
    if (
        not isinstance(path, str)
        or not path.startswith("/")
        or path.startswith("//")
        or "#" in path
        or len(path) > maximum
        or any(ord(character) < 33 for character in path)
    ):
        raise ValueError(
            "request path must be a bounded origin-relative path without whitespace"
        )
    query_component = "query_assertions" in definition
    if not pattern and query_component and "?" in path:
        raise ValueError("path must exclude the query when query_assertions are used")
    headers = definition.get("headers", {})
    if not isinstance(headers, dict) or len(headers) > 100:
        raise ValueError("request headers must be an object of at most 100 fields")
    normalized = {}
    for key, value in headers.items():
        if (
            not isinstance(key, str)
            or not HEADER_NAME.fullmatch(key)
            or not isinstance(value, str)
            or any(character in value for character in "\r\n")
        ):
            raise ValueError("invalid expected request header")
        if key.casefold() in normalized:
            raise ValueError("expected header names must be unique ignoring case")
        normalized[key.casefold()] = value
    json_rules = compile_rules(definition.get("json_assertions", []))
    query_rules = compile_rules(definition.get("query_assertions", []))
    header_rules = compile_rules(definition.get("header_assertions", []))
    for rule in header_rules:
        if rule.tokens and rule.tokens[0] != rule.tokens[0].casefold():
            raise ValueError("header assertion pointers use lowercase header names")
    if "json" in definition:
        validate_json(definition["json"])
    return RequestMatcher(
        method,
        path,
        pattern,
        normalized,
        "json" in definition,
        copy.deepcopy(definition.get("json")),
        json_rules,
        query_rules,
        header_rules,
        query_component,
    )
