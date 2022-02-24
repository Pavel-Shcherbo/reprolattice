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


