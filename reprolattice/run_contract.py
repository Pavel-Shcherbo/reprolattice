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


def validate_run(report):
    validate_json(report, max_bytes=REPORT_LIMIT, max_depth=70, max_nodes=100000)
    validate_report(report)
    named(report.get("suite"), "suite")
    run_id = report.get("run_id")
    if not isinstance(run_id, str) or not CASE_ID.fullmatch(run_id):
        raise ValueError("run ID requires bounded ASCII text")
    sha(report.get("suite_sha256"))
    sha(report.get("definition_sha256"))
    if utc(report.get("started_at")) > utc(report.get("finished_at")):
        raise ValueError("run finish precedes start")
    if "execution_context" in report:
        context(report["execution_context"])
    keys = set()
    excluded = 0
    for case in report["cases"]:
        if not CASE_ID.fullmatch(case["id"]):
            raise ValueError("case ID exceeds archive bounds")
        named(case.get("source_id"), "source case ID")
        if case.get("mode") not in ("application", "protocol", "queue"):
            raise ValueError("unsupported archived case mode")
        if not isinstance(case.get("parameters"), dict):
            raise ValueError("case parameters must be an object")
        sha(case.get("fixture_sha256"))
        sha(case.get("command_sha256"))
        if "parameters_sha256" in case:
            sha(case["parameters_sha256"])
        if "artifact_contract_sha256" in case:
            sha(case["artifact_contract_sha256"])
        if "timeout_seconds" in case and (
            type(case["timeout_seconds"]) not in (int, float)
            or not 0 < case["timeout_seconds"] <= 120
        ):
            raise ValueError("invalid archived case timeout")
        tags = case.get("tags")
        if not isinstance(tags, list) or len(tags) > 20:
            raise ValueError("archived case tags must be a bounded list")
        for tag in tags:
            named(tag, "case tag")
        inputs = case.get("inputs", [])
        states = case.get("sqlite_definitions", [])
        if (
            not isinstance(inputs, list)
            or len(inputs) > 32
            or not isinstance(states, list)
            or len(states) > 4
        ):
            raise ValueError("archived case input/state budget exceeded")
        seen = set()
        for item in inputs:
            if (
                not isinstance(item, dict)
                or set(item) - {"path", "sha256", "bytes", "role"}
                or not {"path", "sha256", "bytes"} <= set(item)
            ):
                raise ValueError("invalid archived input metadata")
            path = relative_path(item["path"])
            sha(item["sha256"])
            if (
                path in seen
                or item.get("role", "fixture") not in ("fixture", "subject")
                or type(item["bytes"]) is not int
                or not 0 <= item["bytes"] <= 4 * 1024 * 1024
            ):
                raise ValueError("invalid or duplicate archived file input")
            seen.add(path)
        seen = set()
        for item in states:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                raise ValueError("invalid archived state definition")
            path = relative_path(item["path"])
            sha(item["sha256"])
            if path in seen:
                raise ValueError("duplicate archived state definition")
            seen.add(path)
        detail = case.get("detail", {})
        if (
            not isinstance(detail, dict)
            or not isinstance(detail.get("checks", {}), dict)
            or any(
                type(value) is not bool for value in detail.get("checks", {}).values()
            )
        ):
            raise ValueError("invalid recorded check structure")
        if "application" in detail and not isinstance(detail["application"], dict):
            raise ValueError("invalid archived application detail")
        if "error" in case and not isinstance(case["error"], dict):
            raise ValueError("invalid archived error detail")
        for key in ("assertions", "results"):
            entries = detail.get(key, [])
            if not isinstance(entries, list) or any(
                not isinstance(item, dict) or type(item.get("passed")) is not bool
                for item in entries
            ):
                raise ValueError("invalid recorded diagnostic entries")
            if key == "assertions" and any(
                not isinstance(item.get("id"), str)
                or not item["id"]
                or len(item["id"]) > 128
                for item in entries
            ):
                raise ValueError("invalid archived assertion ID")
        for key, maximum in (("artifacts", 16), ("sqlite", 4)):
            entries = case.get(key, [])
            if (
                not isinstance(entries, list)
                or len(entries) > maximum
                or any(
                    not isinstance(item, dict) or type(item.get("passed")) is not bool
                    for item in entries
                )
            ):
                raise ValueError("invalid archived output/state checks")
            for item in entries:
                relative_path(item.get("path"))
        if case["status"] == "passed":
            if (
                detail.get("passed") is not True
                or any(value is not True for value in detail.get("checks", {}).values())
                or any(
                    item.get("passed") is not True
                    for item in detail.get("assertions", [])
                )
                or any(
                    item.get("passed") is not True for item in detail.get("results", [])
                )
                or any(
                    item.get("passed") is not True for item in case.get("artifacts", [])
                )
                or any(
                    item.get("passed") is not True for item in case.get("sqlite", [])
                )
            ):
                raise ValueError("passed case contradicts its recorded checks")
        if case["status"] == "skipped" and case.get("reason") == "tag_filter":
            excluded += 1
        key = pair_key(case, modern=True)
        if key in keys:
            raise ValueError(
                "archive contains duplicate source/parameter case identities"
            )
        keys.add(key)
    if report["selected_cases"] != len(report["cases"]) - excluded:
        raise ValueError("selection count contradicts tag-filter exclusions")
    return report


def modern(case):
    return all(
        key in case
        for key in ("parameters_sha256", "artifact_contract_sha256", "timeout_seconds")
    )


def pair_key(case, *, modern):
    if modern and "parameters_sha256" in case:
        return fingerprint(
            {
                "source_id": case["source_id"],
                "parameters_sha256": case["parameters_sha256"],
            }
        )
    return "case:" + case["id"]


def case_identity_parts(case):
    inputs = case.get("inputs", [])
    conditions = {
        "mode": case["mode"],
        "fixture_sha256": case["fixture_sha256"],
        "parameters": case["parameters"],
        "parameters_sha256": case.get("parameters_sha256"),
        "artifact_contract_sha256": case.get("artifact_contract_sha256"),
        "timeout_seconds": case.get("timeout_seconds"),
        "fixtures": sorted(
            (item["path"], item["sha256"])
            for item in inputs
            if item.get("role", "fixture") == "fixture"
        ),
        "sqlite": sorted(
            (item["path"], item["sha256"])
            for item in case.get("sqlite_definitions", [])
        ),
    }
    subject = {
        "command_sha256": case["command_sha256"],
        "files": sorted(
            (item["path"], item["sha256"])
            for item in inputs
            if item.get("role", "fixture") == "subject"
        ),
    }
    return conditions, subject


def case_signatures(case):
    conditions, subject = case_identity_parts(case)
    return fingerprint(conditions), fingerprint(subject)
