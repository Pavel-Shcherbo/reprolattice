"""Explain comparable failures, changed test inputs and lost suite coverage."""

import copy
import math
from collections import Counter

from .reports import failure_summary
from .run_contract import (
    case_signatures,
    case_identity_parts,
    fingerprint,
    modern,
    pair_key,
    validate_run,
)

DEFAULT_POLICY = {
    "version": 1,
    "require_full_suite": True,
    "require_same_context": True,
    "allow_changed_inputs": False,
    "allow_removed": False,
    "allow_new_cases": True,
    "allow_existing_failures": False,
    "allow_legacy_metadata": False,
    "allow_tag_filtered": False,
    "max_slowdown_ratio": None,
    "minimum_duration_seconds": 0.05,
}
BAD = frozenset({"failed", "error"})
EXECUTED = frozenset({"passed", "failed", "error"})


def policy_definition(value=None):
    if value is None:
        return dict(DEFAULT_POLICY)
    if not isinstance(value, dict) or set(value) - set(DEFAULT_POLICY):
        raise ValueError("comparison policy contains unsupported fields")
    result = {**DEFAULT_POLICY, **copy.deepcopy(value)}
    if type(result["version"]) is not int or result["version"] != 1:
        raise ValueError("comparison policy requires version 1")
    for key, default in DEFAULT_POLICY.items():
        if type(default) is bool and type(result[key]) is not bool:
            raise ValueError("comparison boolean policy fields must be booleans")
    ratio = result["max_slowdown_ratio"]
    minimum = result["minimum_duration_seconds"]
    if ratio is not None and (
        type(ratio) not in (int, float)
        or not math.isfinite(ratio)
        or not 1 <= ratio <= 1000000
    ):
        raise ValueError(
            "slowdown ratio must be null or finite between 1 and one million"
        )
    if (
        type(minimum) not in (int, float)
        or not math.isfinite(minimum)
        or not 0 < minimum <= 3600
    ):
        raise ValueError(
            "minimum timing duration must be positive and at most one hour"
        )
    return result


