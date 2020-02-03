"""Verify fixture transport with explicit concrete examples for dynamic matchers."""

import copy
import http.client
import json
import threading

from .assertions import json_equal
from .jsonutil import strict_json
from .matching import compile_request
from .redaction import redact
from .replay import make_server, validate


def sample_request(item):
    definition = item["request"]
    sample = item.get("sample_request")
    dynamic = any(
        key in definition
        for key in (
            "path_pattern",
            "json_assertions",
            "query_assertions",
            "header_assertions",
        )
    )
    if sample is None:
        if dynamic:
            raise ValueError(
                "dynamic request rules require sample_request for protocol verification"
            )
        sample = copy.deepcopy(definition)
    if not isinstance(sample, dict) or set(sample) - {
        "method",
        "path",
        "headers",
        "json",
    }:
        raise ValueError("sample_request supports only method, path, headers and json")
    compile_request(sample)
    issues = compile_request(definition).match(
        sample["method"], sample["path"], sample.get("json"), sample.get("headers", {})
    )
    if issues:
        raise ValueError("sample_request does not satisfy its request matcher")
    return sample


