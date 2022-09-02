"""Local archive controls over saved suite evidence; no arbitrary command execution."""

import sqlite3

from .reports import junit_xml
from .resources import state_directory
from .run_contract import fingerprint, sha, validate_run
from .run_registry import RunRegistry
from .suite_config import named

PROJECT = "inventory-workbench"
FIELDS = {
    "overview": {"after", "baseline_after"},
    "archive": {"report", "request_key", "label"},
    "inspect": {"record"},
    "baseline": {"name", "after"},
    "move": {"name", "record", "generation", "reason"},
    "compare": {"record", "before", "baseline", "generation"},
    "history": {"source", "after", "status"},
    "junit": {"record"},
}


def cursor(value, label="cursor"):
    if type(value) is not int or not 0 <= value <= 9223372036854775807:
        raise ValueError(label + " must be a bounded nonnegative integer")
    return value


def evaluate_archive(params):
    if not isinstance(params, dict):
        raise ValueError("archive request requires an object")
    action = params.get("action", "overview")
    if (
        not isinstance(action, str)
        or action not in FIELDS
        or set(params) - ({"mode", "action"} | FIELDS.get(action, set()))
    ):
        raise ValueError("unknown archive action or unsupported fields")
    if "record" in FIELDS[action]:
        sha(params.get("record"))
    if "after" in params:
        cursor(params["after"])
    if "generation" in params:
        cursor(params["generation"], "baseline generation")
    if action in ("baseline", "move"):
        named(params.get("name"), "baseline")
    if action == "overview" and params.get("baseline_after", "") != "":
        named(params["baseline_after"], "baseline cursor")
    if action == "archive":
        report = params.get("report")
        validate_run(report)
        named(params.get("request_key"), "request key")
        label = params.get("label", "")
        if not isinstance(label, str) or len(label) > 128:
            raise ValueError("archive label must be text of at most 128 characters")
    if action == "move":
        cursor(params.get("generation"), "baseline generation")
        reason = params.get("reason")
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 512:
            raise ValueError("baseline move requires a reason of 1–512 characters")
    if action == "compare":
        if "before" in params:
            if "baseline" in params or "generation" in params:
                raise ValueError("choose an archived run or a named baseline reference")
            sha(params["before"])
        else:
            named(params.get("baseline"), "baseline")
            cursor(params.get("generation"), "baseline generation")
            if not params["generation"]:
                raise ValueError("comparison baseline must already exist")
    if action == "history":
        named(params.get("source"), "source case")
        status = params.get("status")
        if status is not None and (
            not isinstance(status, str)
            or status not in ("passed", "failed", "error", "skipped", "cancelled")
        ):
            raise ValueError("unknown case history status")
    database = state_directory("reprolattice") / "run-workbench" / "runs.sqlite"
    try:
        if not database.exists() and action == "overview":
            return {
                "initialized": False,
                "items": [],
                "next_cursor": None,
                "baselines": {"items": [], "next_cursor": None},
            }
        registry = RunRegistry(database, create=action == "archive")
        if action == "archive":
            # This is a content identity derived from supplied evidence, not a Git attestation.
            subjects = [
                {
                    "source_id": case["source_id"],
                    "command_sha256": case["command_sha256"],
                    "subject_inputs": [
                        item
                        for item in case.get("inputs", [])
                        if item.get("role", "fixture") == "subject"
                    ],
                }
                for case in report["cases"]
            ]
            revision = fingerprint(
                {"format": "reprolattice.subject-content.v1", "subjects": subjects}
            )
            registry.project(PROJECT)
            record = registry.record(
                PROJECT,
                report,
                revision=revision,
                request_key=params["request_key"],
                label=label,
            )
            return {
                "record": record,
                "revision_scope": "Content identifier derived from supplied report metadata; not authenticated Git provenance.",
            }
        if action == "overview":
            return {
                "initialized": True,
                **registry.list(
                    PROJECT, after=params.get("after", 0), limit=25, order="newest"
                ),
                "baselines": registry.baselines(
                    PROJECT, after=params.get("baseline_after", ""), limit=25
                ),
            }
        if action == "inspect":
            return {"record": registry.get(PROJECT, params["record"])}
        if action == "baseline":
            return registry.baseline_view(
                PROJECT, params["name"], after=params.get("after", 0), limit=25
            )
        if action == "move":
            return registry.move_baseline(
                PROJECT,
                params["name"],
                params["record"],
                expected_generation=params["generation"],
                reason=params["reason"],
            )
        if action == "compare":
            if "before" in params:
                return registry.compare(PROJECT, params["before"], params["record"])
            return registry.compare_baseline(
                PROJECT,
                params["baseline"],
                params["record"],
                expected_generation=params["generation"],
            )
        if action == "history":
            return registry.history(
                PROJECT,
                params["source"],
                after=params.get("after", 0),
                limit=25,
                status=params.get("status"),
            )
        return {
            "record": params["record"],
            "junit_xml": junit_xml(
                registry.get(PROJECT, params["record"])["report"]
            ).decode(),
        }
    except sqlite3.Error as error:
        raise ValueError("local archive database: " + str(error)) from error
