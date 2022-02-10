"""Explain comparable failures, changed test inputs and lost suite coverage."""

import copy
import math
from collections import Counter

from .reports import failure_summary
from .run_contract import (
    case_signatures,
    case_identity_parts,
    fingerprint,
    modern,
    pair_key,
    validate_run,
)

DEFAULT_POLICY = {
    "version": 1,
    "require_full_suite": True,
    "require_same_context": True,
    "allow_changed_inputs": False,
    "allow_removed": False,
    "allow_new_cases": True,
    "allow_existing_failures": False,
    "allow_legacy_metadata": False,
    "allow_tag_filtered": False,
    "max_slowdown_ratio": None,
    "minimum_duration_seconds": 0.05,
}
BAD = frozenset({"failed", "error"})
EXECUTED = frozenset({"passed", "failed", "error"})


def policy_definition(value=None):
    if value is None:
        return dict(DEFAULT_POLICY)
    if not isinstance(value, dict) or set(value) - set(DEFAULT_POLICY):
        raise ValueError("comparison policy contains unsupported fields")
    result = {**DEFAULT_POLICY, **copy.deepcopy(value)}
    if type(result["version"]) is not int or result["version"] != 1:
        raise ValueError("comparison policy requires version 1")
    for key, default in DEFAULT_POLICY.items():
        if type(default) is bool and type(result[key]) is not bool:
            raise ValueError("comparison boolean policy fields must be booleans")
    ratio = result["max_slowdown_ratio"]
    minimum = result["minimum_duration_seconds"]
    if ratio is not None and (
        type(ratio) not in (int, float)
        or not math.isfinite(ratio)
        or not 1 <= ratio <= 1000000
    ):
        raise ValueError(
            "slowdown ratio must be null or finite between 1 and one million"
        )
    if (
        type(minimum) not in (int, float)
        or not math.isfinite(minimum)
        or not 0 < minimum <= 3600
    ):
        raise ValueError(
            "minimum timing duration must be positive and at most one hour"
        )
    return result


def comparison(before, after, *, before_context=None, after_context=None, policy=None):
    validate_run(before)
    validate_run(after)
    policy = policy_definition(policy)
    if before["suite"] != after["suite"]:
        raise ValueError("run comparison requires the same suite name")
    before_context = before_context or {}
    after_context = after_context or {}
    modern_pairing = all(
        modern(case) for report in (before, after) for case in report["cases"]
    )
    left = {pair_key(case, modern=modern_pairing): case for case in before["cases"]}
    right = {pair_key(case, modern=modern_pairing): case for case in after["cases"]}
    findings = []
    changes = []

    def finding(code, case=None, **detail):
        findings.append(
            {"code": code, **({"case": case} if case is not None else {}), **detail}
        )

    if not modern_pairing and not policy["allow_legacy_metadata"]:
        finding("legacy_identity_metadata")
    if policy["require_full_suite"]:
        if not before["full_suite"]:
            finding("baseline_not_full_suite")
        if not after["full_suite"]:
            finding("candidate_not_full_suite")
    context_changes = [
        {"key": key, "before": before_context.get(key), "after": after_context.get(key)}
        for key in sorted(set(before_context) | set(after_context))
        if before_context.get(key) != after_context.get(key)
    ]
    if policy["require_same_context"] and (not before_context or not after_context):
        finding("execution_context_unavailable")
    if context_changes and policy["require_same_context"]:
        finding(
            "execution_context_changed",
            fields=[item["key"] for item in context_changes],
        )
    for key in sorted(set(left) | set(right)):
        a = left.get(key)
        b = right.get(key)
        item = {
            "match_key": key,
            "before_case": a["id"] if a else None,
            "after_case": b["id"] if b else None,
            "before_status": a["status"] if a else None,
            "after_status": b["status"] if b else None,
            "inputs_changed": False,
            "subject_changed": False,
            "slowdown": False,
            "coverage_lost": bool(
                a and b and a["status"] in EXECUTED and b["status"] not in EXECUTED
            ),
            "input_change_fields": [],
            "subject_change_fields": [],
        }
        if a is None:
            item["classification"] = "added_" + (
                "pass"
                if b["status"] == "passed"
                else "failure" if b["status"] in BAD else "unexecuted"
            )
            if not policy["allow_new_cases"]:
                finding("case_added", b["id"])
        elif b is None:
            item["classification"] = "removed"
            if not policy["allow_removed"]:
                finding("case_removed", a["id"])
        else:
            a_conditions, a_subject_fields = case_identity_parts(a)
            b_conditions, b_subject_fields = case_identity_parts(b)
            item["input_change_fields"] = [
                field
                for field in a_conditions
                if a_conditions[field] != b_conditions[field]
            ]
            item["subject_change_fields"] = [
                field
                for field in a_subject_fields
                if a_subject_fields[field] != b_subject_fields[field]
            ]
            a_input, a_subject = case_signatures(a)
            b_input, b_subject = case_signatures(b)
            item.update(
                inputs_changed=a_input != b_input,
                subject_changed=a_subject != b_subject,
                before_inputs_sha256=a_input,
                after_inputs_sha256=b_input,
                before_subject_sha256=a_subject,
                after_subject_sha256=b_subject,
            )
            if item["inputs_changed"]:
                item["classification"] = "changed_inputs"
                if not policy["allow_changed_inputs"]:
                    finding("test_inputs_changed", b["id"])
            elif a["status"] == "passed" and b["status"] in BAD:
                item["classification"] = "regressed"
            elif a["status"] in BAD and b["status"] == "passed":
                item["classification"] = "fixed"
            elif a["status"] in EXECUTED and b["status"] not in EXECUTED:
                item["classification"] = "lost_coverage"
            elif a["status"] not in EXECUTED and b["status"] in EXECUTED:
                item["classification"] = "newly_executed"
            elif b["status"] == "passed":
                item["classification"] = "stable_pass"
            elif b["status"] in BAD:
                item["classification"] = (
                    "changed_failure"
                    if failure_summary(a) != failure_summary(b)
                    else "stable_failure"
                )
            else:
                item["classification"] = "not_executed"
            if not item["inputs_changed"] and a["status"] == b["status"] == "passed":
                item["duration_ratio"] = (
                    b["duration_seconds"] / a["duration_seconds"]
                    if a["duration_seconds"] > 0
                    else None
                )
                overflow = item["duration_ratio"] is not None and not math.isfinite(
                    item["duration_ratio"]
                )
                item["duration_ratio_overflow"] = overflow
                if overflow:
                    item["duration_ratio"] = None
                ratio = policy["max_slowdown_ratio"]
                if (
                    ratio is not None
                    and a["duration_seconds"] >= policy["minimum_duration_seconds"]
                    and (overflow or item["duration_ratio"] > ratio)
                ):
                    item["slowdown"] = True
                    finding(
                        "single_run_slowdown", b["id"], ratio=item["duration_ratio"]
                    )
        if b is not None:
            if b["status"] in BAD:
                existing = (
                    a is not None and a["status"] in BAD and not item["inputs_changed"]
                )
                if not existing or not policy["allow_existing_failures"]:
                    finding(
                        (
                            "regression"
                            if item["classification"] == "regressed"
                            else "candidate_failure"
                        ),
                        b["id"],
                        status=b["status"],
                    )
            elif b["status"] not in EXECUTED:
                excluded = b["status"] == "skipped" and b.get("reason") == "tag_filter"
                if not excluded or not policy["allow_tag_filtered"]:
                    finding(
                        "case_not_executed",
                        b["id"],
                        status=b["status"],
                        reason=b.get("reason"),
                    )
            if b["status"] in BAD:
                item["after_failure"] = failure_summary(b)[:4096]
        if a is not None and a["status"] in BAD:
            item["before_failure"] = failure_summary(a)[:4096]
        changes.append(item)
    result = {
        "format": "reprolattice.run-comparison.v1",
        "suite": before["suite"],
        "before_run_id": before["run_id"],
        "after_run_id": after["run_id"],
        "pairing_policy": (
            "source_and_parameter_digest" if modern_pairing else "legacy_case_id"
        ),
        "policy": policy,
        "context_changes": context_changes,
        "before_full_suite": before["full_suite"],
        "after_full_suite": after["full_suite"],
        "counts": dict(
            sorted(Counter(item["classification"] for item in changes).items())
        ),
        "subject_changed_cases": sum(item["subject_changed"] for item in changes),
        "changed_input_cases": sum(item["inputs_changed"] for item in changes),
        "lost_coverage_cases": sum(item["coverage_lost"] for item in changes),
        "changes": changes,
        "gate": {"passed": not findings, "findings": findings},
        "timing_scope": "Single-run observed durations; no statistical performance-confidence claim.",
        "scope": "Recorded suite evidence only; source revisions/context are caller declarations, not authenticated provenance.",
    }
    result["sha256"] = fingerprint(result)
    return result
