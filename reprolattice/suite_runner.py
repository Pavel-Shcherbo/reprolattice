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


def run_case(case, workspace, should_cancel):
    started = time.monotonic()
    result = {**case_metadata(case), "started_at": utc_now()}
    if should_cancel():
        return scrub(
            {
                **result,
                "status": "cancelled",
                "reason": "cancelled_before_start",
                "duration_seconds": 0,
            },
            case.secrets,
        )
    try:
        workspace.mkdir()
        for item in case.files:
            target = workspace / item.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item.content)
        deadline = started + case.timeout

        def case_cancelled():
            return should_cancel() or time.monotonic() >= deadline

        if case.mode == "application":
            detail = check_client(
                case.fixture,
                list(case.command),
                max(0.001, deadline - time.monotonic()),
                workspace,
                should_cancel=case_cancelled,
            )
        else:
            detail = verify_protocol(case.fixture, should_cancel=case_cancelled)
        if time.monotonic() >= deadline and not should_cancel():
            detail["cancelled"] = False
            detail["passed"] = False
            detail.setdefault("checks", {})["within_case_time_limit"] = False
        artifacts = (
            check_artifacts(workspace, case.artifacts)
            if not detail.get("cancelled")
            else []
        )
        if should_cancel():
            detail["cancelled"], detail["passed"] = True, False
        elif time.monotonic() >= deadline:
            detail["cancelled"], detail["passed"] = False, False
            detail.setdefault("checks", {})["within_case_time_limit"] = False
        status = (
            "cancelled"
            if detail.get("cancelled")
            else (
                "passed"
                if detail["passed"] and all(item["passed"] for item in artifacts)
                else "failed"
            )
        )
        result.update(
            status=status,
            detail=compact_detail(detail),
            artifacts=compact_detail({"items": artifacts})["items"],
        )
    except Exception as error:
        result.update(
            status="error",
            error={"type": type(error).__name__, "message": str(error)[:8192]},
        )
    result["duration_seconds"] = time.monotonic() - started
    return scrub(result, case.secrets)


