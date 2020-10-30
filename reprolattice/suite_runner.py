"""Bounded concurrent suite execution with deterministic result ordering."""

import hashlib
import json
import tempfile
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path

from .artifact_checks import check_artifacts
from .harness import check_client
from .parameters import scrub
from .protocol import verify_protocol
from .suite_config import SuitePlan, named


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def compact_detail(detail):
    """Preserve check outcomes while bounding retained payload diagnostics."""
    result = dict(detail)
    if "application" in result:
        application = dict(result["application"])
        output = application.pop("output", None)
        encoded = json.dumps(output, sort_keys=True, allow_nan=False).encode()
        application["output_summary"] = {
            "type": {
                dict: "object",
                list: "array",
                bool: "boolean",
                int: "number",
                float: "number",
                str: "string",
                type(None): "null",
            }[type(output)],
            "bytes": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
        }
        result["application"] = application
    if "results" in result:
        result["results"] = [
            {key: value for key, value in row.items() if key != "body"}
            for row in result["results"]
        ]
    if len(json.dumps(result, allow_nan=False).encode()) > 128 * 1024:

        def reduce(item):
            if isinstance(item, dict):
                return {
                    key: reduce(value)
                    for key, value in item.items()
                    if key not in ("actual", "expected")
                }
            if isinstance(item, list):
                return [reduce(value) for value in item]
            return item

        result = reduce(result)
        result["value_diagnostics_omitted"] = True
    return result


def case_metadata(case):
    return {
        "id": case.id,
        "source_id": case.source_id,
        "mode": case.mode,
        "tags": list(case.tags),
        "parameters": case.parameters,
        "fixture_sha256": case.fixture_sha256,
        "command_sha256": hashlib.sha256(
            json.dumps(case.command, separators=(",", ":")).encode()
        ).hexdigest(),
        "inputs": [
            {"path": item.path, "sha256": item.sha256, "bytes": len(item.content)}
            for item in case.files
        ],
    }


