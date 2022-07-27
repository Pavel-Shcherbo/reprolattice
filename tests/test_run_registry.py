"""Archive immutability, baseline fencing and independently classified regressions."""

import copy
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

from reprolattice.run_contract import fingerprint, validate_run
from reprolattice.run_compare import comparison
from reprolattice.run_registry import RunRegistry
from reprolattice.suite_config import compile_suite
from reprolattice.suite_runner import run_suite

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
CONTEXT = {"runner": "controlled-test"}


def report(statuses=("passed",), *, names=None, full=True):
    cases = []
    for index, status in enumerate(statuses):
        name = names[index] if names else "case-" + str(index + 1)
        case = {
            "id": name,
            "source_id": name,
            "mode": "application",
            "tags": ["unit"],
            "parameters": {},
            "parameters_sha256": fingerprint({}),
            "artifact_contract_sha256": fingerprint([]),
            "timeout_seconds": 10,
            "fixture_sha256": "a" * 64,
            "command_sha256": "b" * 64,
            "inputs": [],
            "sqlite_definitions": [],
            "status": status,
            "duration_seconds": 1.0,
        }
        if status in ("passed", "failed", "error"):
            case["detail"] = {
                "passed": status == "passed",
                "checks": {"value": status == "passed"},
            }
        if status == "error":
            case["error"] = {"type": "RuntimeError", "message": "controlled error"}
        if status == "skipped":
            case["reason"] = "tag_filter" if not full else "fail_fast"
        cases.append(case)
    counts = {
        status: sum(c["status"] == status for c in cases)
        for status in ("passed", "failed", "error", "skipped", "cancelled")
    }
    selected = len(cases) - sum(c.get("reason") == "tag_filter" for c in cases)
    passed = counts["passed"] == selected and not any(
        counts[key] for key in ("failed", "error", "cancelled")
    )
    return {
        "format": "reprolattice.suite-report.v1",
        "suite": "controlled",
        "run_id": str(uuid.uuid4()),
        "suite_sha256": "c" * 64,
        "definition_sha256": "d" * 64,
        "started_at": "2026-11-04T10:00:00Z",
        "finished_at": "2026-11-04T10:00:02Z",
        "duration_seconds": 2.0,
        "execution_context": CONTEXT,
        "selected_cases": selected,
        "total_cases": len(cases),
        "full_suite": selected == len(cases),
        "passed": passed,
        "counts": counts,
        "cases": cases,
    }


