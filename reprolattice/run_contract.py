"""Archive and comparison identities for bounded suite execution evidence."""

import hashlib
import json
import re
from datetime import datetime, timezone

from .jsonutil import validate_json
from .reports import validate_report
from .suite_config import named, relative_path

SHA = re.compile(r"^[0-9a-f]{64}$")
REVISION = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
CASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
REPORT_LIMIT = 8 * 1024 * 1024


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def fingerprint(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sha(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError("run identities require lowercase SHA-256")
    return value


def utc(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("run timestamps require bounded timezone-aware ISO text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("invalid run timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError("run timestamps require a timezone")
    try:
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as error:
        raise ValueError("run timestamp is outside the UTC range") from error


def context(value):
    validate_json(value, max_bytes=16384, max_depth=5, max_nodes=1000)
    if (
        not isinstance(value, dict)
        or len(value) > 32
        or any(
            not isinstance(key, str)
            or not key
            or len(key) > 64
            or not isinstance(item, str)
            or len(item) > 1024
            for key, item in value.items()
        )
    ):
        raise ValueError("run context requires at most 32 bounded text fields")
    return dict(value)


