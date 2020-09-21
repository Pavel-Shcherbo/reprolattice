"""Portable JSON, JUnit-compatible XML and escaped standalone HTML suite reports."""

import html
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

INVALID_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")
STATUSES = ("passed", "failed", "error", "skipped", "cancelled")


def xml_text(value):
    return INVALID_XML.sub("\ufffd", str(value))


def validate_report(report):
    if (
        not isinstance(report, dict)
        or report.get("format") != "reprolattice.suite-report.v1"
    ):
        raise ValueError("unsupported suite report format")
    cases = report.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 256:
        raise ValueError("suite report requires 1–256 case records")
    for case in cases:
        if not isinstance(case, dict) or case.get("status") not in STATUSES:
            raise ValueError("report case has an invalid status")
        duration = case.get("duration_seconds")
        if type(duration) not in (int, float) or not 0 <= duration < 86400:
            raise ValueError("report case has an invalid duration")
    counts = {
        status: sum(case["status"] == status for case in cases) for status in STATUSES
    }
    identifiers = [case.get("id") for case in cases]
    if any(not isinstance(name, str) or not name for name in identifiers) or len(
        set(identifiers)
    ) != len(identifiers):
        raise ValueError("report case IDs must be unique non-empty strings")
    duration = report.get("duration_seconds")
    if type(duration) not in (int, float) or not 0 <= duration < 86400:
        raise ValueError("report duration is invalid")
    selected = report.get("selected_cases")
    if type(selected) is not int or not 1 <= selected <= len(cases):
        raise ValueError("report selected case count is invalid")
    expected_pass = counts["passed"] == selected and not any(
        counts[status] for status in ("failed", "error", "cancelled")
    )
    if (
        type(report.get("passed")) is not bool
        or report["passed"] != expected_pass
        or report.get("full_suite") != (selected == len(cases))
    ):
        raise ValueError("report completion flags contradict its case results")
    declared = report.get("counts")
    if (
        not isinstance(declared, dict)
        or set(declared) != set(STATUSES)
        or any(type(value) is not int or value < 0 for value in declared.values())
    ):
        raise ValueError("report counts must be nonnegative integers")
    if (
        type(report.get("full_suite")) is not bool
        or type(report.get("total_cases")) is not int
    ):
        raise ValueError("report scope fields have invalid types")
    if counts != declared or report.get("total_cases") != len(cases):
        raise ValueError("suite report counts do not match case records")
    return report


