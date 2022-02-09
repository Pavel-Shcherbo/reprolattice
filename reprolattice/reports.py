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
        "SQLite " + state["path"]
        for state in case.get("sqlite", [])
        if not state["passed"]
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


def html_report(report):
    validate_report(report)
    escape = lambda value: html.escape(str(value), quote=True)
    cards = []
    for case in report["cases"]:
        status = case["status"]
        detail = json.dumps(
            {
                "checks": case.get("detail", {}).get("checks", {}),
                "assertions": case.get("detail", {}).get("assertions", []),
                "artifacts": case.get("artifacts", []),
                "error": case.get("error"),
            },
            indent=2,
            ensure_ascii=True,
        )
        cards.append(
            f"""<tr><td><details><summary>{escape(case['id'])}</summary><p>{escape(failure_summary(case))}</p><pre>{escape(detail)}</pre></details></td><td class="{status}">{status}</td><td class="number">{case['duration_seconds']:.3f}</td><td>{escape(', '.join(case['tags']))}</td></tr>"""
        )
    counts = " · ".join(f'{report["counts"][status]} {status}' for status in STATUSES)
    scope = (
        "Full suite"
        if report["full_suite"]
        else f'Selected {report["selected_cases"]} of {report["total_cases"]} cases'
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>{escape(report['suite'])} — Reprolattice run</title><style>
:root {{ color-scheme: light; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; padding: 32px 24px; color: #243039; background: #f5f7f8; font: 15px/1.6 system-ui,sans-serif; }}
main {{ max-width: 1100px; margin: auto; }} h1 {{ font-size: 28px; font-weight: 600; margin: 8px 0; }}
p {{ max-width: 80ch; }} .meta {{ color: #52616c; overflow-wrap: anywhere; }}
.tablewrap {{ overflow-x: auto; background: white; border: 1px solid #d9e0e4; border-radius: 8px; }}
table {{ width: 100%; border-collapse: collapse; }} th,td {{ padding: 16px; border-bottom: 1px solid #e4e9ec; text-align: left; vertical-align: top; }}
th {{ font-weight: 600; background: #edf1f3; }} .number {{ text-align: right; font-variant-numeric: tabular-nums; }}
summary {{ cursor: pointer; overflow-wrap: anywhere; }} pre {{ max-width: 65ch; overflow: auto; font-size: 12px; }}
.passed {{ color: #166243; }} .failed,.error {{ color: #9f2630; }} .skipped,.cancelled {{ color: #6a531f; }}
:focus-visible {{ outline: 3px solid #37688e; outline-offset: 3px; }}
@media(max-width:600px) {{ body {{ padding:16px; }} th,td {{ padding:12px; }} }}
</style></head><body><main><p class="meta">Reprolattice local run report</p><h1>{escape(report['suite'])}</h1>
<p>{escape(scope)}. {'Checks passed' if report['passed'] else 'Review unsuccessful or incomplete cases'}.</p>
<p>{escape(counts)}</p><p class="meta">Started {escape(report['started_at'])}; elapsed {report['duration_seconds']:.3f} seconds</p>
<div class="tablewrap"><table><thead><tr><th>Case and checks</th><th>Status</th><th class="number">Seconds</th><th>Tags</th></tr></thead><tbody>{''.join(cards)}</tbody></table></div>
<p class="meta">Run {escape(report['run_id'])}<br>Suite SHA-256 {escape(report['suite_sha256'])}</p>
<p class="meta">Expand a case to inspect its checks. Skipped and cancelled cases are recorded explicitly.</p>
</main></body></html>"""


def write_reports(report, directory):
    validate_report(report)
    requested = Path(directory).expanduser()
    if requested.is_symlink():
        raise ValueError("report destination cannot be a symbolic link")
    destination = requested.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payloads = {
        "report.json": (json.dumps(report, indent=2, allow_nan=False) + "\n").encode(),
        "junit.xml": junit_xml(report),
        "report.html": html_report(report).encode(),
    }
    if sum(len(payload) for payload in payloads.values()) > 64 * 1024 * 1024:
        raise ValueError("combined suite reports exceed 64 MiB")
    temporary = Path(
        tempfile.mkdtemp(prefix=".reprolattice-report-", dir=destination.parent)
    )
    reserved = False
    try:
        for name, payload in payloads.items():
            with (temporary / name).open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        # Reserve without replacing even an empty directory. Consumers should use
        # manifest.json as the completion marker, written after all report files.
        destination.mkdir()
        reserved = True
        for name in payloads:
            os.replace(temporary / name, destination / name)
        manifest = {
            "format": "reprolattice.report-set.v1",
            "run_id": report["run_id"],
            "files": {
                name: {
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
                for name, payload in payloads.items()
            },
        }
        with (temporary / "manifest.json").open("x") as stream:
            json.dump(manifest, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary / "manifest.json", destination / "manifest.json")
        return manifest
    except BaseException:
        if reserved:
            shutil.rmtree(destination)
        raise
    finally:
        shutil.rmtree(temporary)
