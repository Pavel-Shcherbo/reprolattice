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


def failure_summary(case):
    if case["status"] == "error":
        return case.get("error", {}).get("message", "case execution error")
    detail = case.get("detail", {})
    messages = [name for name, passed in detail.get("checks", {}).items() if not passed]
    messages += [
        "assertion " + rule["id"]
        for rule in detail.get("assertions", [])
        if not rule["passed"]
    ]
    messages += [
        "artifact " + artifact["path"]
        for artifact in case.get("artifacts", [])
        if not artifact["passed"]
    ]
    messages += [
        "request " + str(index + 1)
        for index, result in enumerate(detail.get("results", []))
        if not result["passed"]
    ]
    return "; ".join(messages) or case.get("reason", case["status"])


def junit_xml(report):
    validate_report(report)
    counts = report["counts"]
    suite = ET.Element(
        "testsuite",
        {
            "name": xml_text(report["suite"]),
            "tests": str(len(report["cases"])),
            "failures": str(counts["failed"]),
            "errors": str(counts["error"]),
            "skipped": str(counts["skipped"] + counts["cancelled"]),
            "time": f'{report["duration_seconds"]:.6f}',
            "timestamp": xml_text(report["started_at"]),
        },
    )
    properties = ET.SubElement(suite, "properties")
    for name, value in [
        ("run_id", report["run_id"]),
        ("suite_sha256", report["suite_sha256"]),
        ("full_suite", report["full_suite"]),
        ("selected_cases", report["selected_cases"]),
        ("cancelled_cases", counts["cancelled"]),
    ]:
        ET.SubElement(properties, "property", {"name": name, "value": xml_text(value)})
    for case in report["cases"]:
        node = ET.SubElement(
            suite,
            "testcase",
            {
                "classname": xml_text(report["suite"]),
                "name": xml_text(case["id"]),
                "time": f'{case["duration_seconds"]:.6f}',
            },
        )
        status = case["status"]
        if status in ("failed", "error"):
            failure = ET.SubElement(
                node,
                "failure" if status == "failed" else "error",
                {"message": xml_text(failure_summary(case)), "type": xml_text(status)},
            )
            failure.text = xml_text(
                json.dumps(
                    {
                        "detail": case.get("detail"),
                        "artifacts": case.get("artifacts"),
                        "error": case.get("error"),
                    },
                    indent=2,
                    ensure_ascii=True,
                )
            )
        elif status in ("skipped", "cancelled"):
            skipped = ET.SubElement(
                node,
                "skipped",
                {"message": xml_text(case.get("reason", status)), "type": status},
            )
            skipped.text = xml_text(case.get("reason", status))
        stderr = case.get("detail", {}).get("application", {}).get("stderr")
        if stderr:
            ET.SubElement(node, "system-err").text = xml_text(stderr)
    root = ET.Element("testsuites")
    root.append(suite)
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


