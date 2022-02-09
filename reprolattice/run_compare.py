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


