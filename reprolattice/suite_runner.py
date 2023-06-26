"""Bounded concurrent suite execution with deterministic result ordering."""

import hashlib
import json
import tempfile
import threading
import time
import uuid
import platform
from dataclasses import asdict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path

from .artifact_checks import check_artifacts
from .harness import check_client
from .parameters import scrub
from .protocol import verify_protocol
from .suite_config import SuitePlan, named
from .sqlite_state import prepare_states, inspect_states


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
        "parameters_sha256": hashlib.sha256(
            json.dumps(
                case.parameters, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest(),
        "artifact_contract_sha256": hashlib.sha256(
            json.dumps(
                [asdict(item) for item in case.artifacts],
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest(),
        "timeout_seconds": case.timeout,
        "fixture_sha256": case.fixture_sha256,
        "command_sha256": hashlib.sha256(
            json.dumps(case.command, separators=(",", ":")).encode()
        ).hexdigest(),
        "sqlite_definitions": [
            {"path": state.path, "sha256": state.sha256} for state in case.states
        ],
        "inputs": [
            {
                "path": item.path,
                "sha256": item.sha256,
                "bytes": len(item.content),
                "role": item.role,
            }
            for item in case.files
        ],
    }


def run_case(case, workspace, should_cancel, on_state=None):
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

        prepared = prepare_states(workspace, case.states, should_cancel=case_cancelled)
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
        states = (
            inspect_states(
                workspace,
                prepared,
                should_cancel=case_cancelled,
                on_snapshot=(
                    (lambda state, before, after: on_state(case, state, before, after))
                    if on_state is not None
                    else None
                ),
            )
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
                if detail["passed"]
                and all(item["passed"] for item in artifacts)
                and all(item["passed"] for item in states)
                else "failed"
            )
        )
        result.update(
            status=status,
            detail=compact_detail(detail),
            artifacts=compact_detail({"items": artifacts})["items"],
            sqlite=compact_detail({"items": states})["items"],
        )
    except Exception as error:
        if should_cancel():
            result.update(
                status="cancelled", reason="cancelled_during_state_setup_or_inspection"
            )
        elif time.monotonic() >= started + case.timeout:
            result.update(status="failed", reason="case_time_limit_exceeded")
        else:
            result.update(
                status="error",
                error={"type": type(error).__name__, "message": str(error)[:8192]},
            )
    result["duration_seconds"] = time.monotonic() - started
    return scrub(result, case.secrets)


def run_suite(
    plan,
    *,
    jobs=1,
    fail_fast=False,
    include_tags=(),
    exclude_tags=(),
    should_cancel=None,
    on_event=None,
    on_state=None,
):
    if not isinstance(plan, SuitePlan):
        raise ValueError("run_suite requires a compiled SuitePlan")
    if type(jobs) is not int or not 1 <= jobs <= 8:
        raise ValueError("jobs must be between one and eight")
    if type(fail_fast) is not bool:
        raise ValueError("fail_fast must be boolean")
    for callback in (should_cancel, on_event, on_state):
        if callback is not None and not callable(callback):
            raise ValueError("suite callbacks must be callable")
    for selection in (include_tags, exclude_tags):
        if not isinstance(selection, (tuple, list)) or len(selection) > 20:
            raise ValueError("tag selection requires at most 20 labels")
        for tag in selection:
            named(tag, "selection tag")
    selected = [
        case
        for case in plan.cases
        if (not include_tags or set(case.tags) & set(include_tags))
        and not set(case.tags) & set(exclude_tags)
    ]
    if not selected:
        raise ValueError("tag selection excludes every case")
    started, wall_start = utc_now(), time.monotonic()
    stop = threading.Event()
    stop_reason = None
    results, events, event_sequence = {}, [], 0

    def emit(kind, case_id, **payload):
        nonlocal event_sequence
        event_sequence += 1
        event = {
            "sequence": event_sequence,
            "kind": kind,
            "case_id": case_id,
            **payload,
        }
        events.append(event)
        if on_event is not None:
            on_event(dict(event))

    def cancelled():
        return stop.is_set() or (should_cancel is not None and should_cancel())

    chosen = {case.id for case in selected}
    for case in plan.cases:
        if case.id not in chosen:
            results[case.id] = scrub(
                {
                    **case_metadata(case),
                    "status": "skipped",
                    "reason": "tag_filter",
                    "duration_seconds": 0,
                },
                case.secrets,
            )
    next_case, pending = 0, {}
    with tempfile.TemporaryDirectory(prefix="reprolattice-suite-") as temporary:
        executor = ThreadPoolExecutor(max_workers=jobs)
        try:
            while next_case < len(selected) or pending:
                if should_cancel is not None and should_cancel():
                    stop_reason = "user_cancelled"
                    stop.set()
                while (
                    not stop.is_set()
                    and next_case < len(selected)
                    and len(pending) < jobs
                ):
                    case = selected[next_case]
                    next_case += 1
                    emit("case_started", case.id)
                    future = executor.submit(
                        run_case, case, Path(temporary) / case.id, cancelled, on_state
                    )
                    pending[future] = case
                if not pending:
                    break
                done, _ = wait(pending, timeout=0.05, return_when=FIRST_COMPLETED)
                # Completion arrival order is operational; report order stays the
                # original suite order, independent of worker scheduling.
                for future in sorted(done, key=lambda item: pending[item].id):
                    case = pending.pop(future)
                    result = future.result()
                    results[case.id] = result
                    emit("case_finished", case.id, status=result["status"])
                    if (
                        fail_fast
                        and result["status"] in ("failed", "error")
                        and not stop.is_set()
                    ):
                        stop_reason = "fail_fast"
                        stop.set()
            for case in selected[next_case:]:
                status = "cancelled" if stop_reason == "user_cancelled" else "skipped"
                results[case.id] = scrub(
                    {
                        **case_metadata(case),
                        "status": status,
                        "reason": stop_reason or "not_started",
                        "duration_seconds": 0,
                    },
                    case.secrets,
                )
                emit("case_not_started", case.id, status=status)
        finally:
            stop.set()
            executor.shutdown(wait=True, cancel_futures=True)
    ordered = [results[case.id] for case in plan.cases]
    counts = {
        status: sum(item["status"] == status for item in ordered)
        for status in ("passed", "failed", "error", "skipped", "cancelled")
    }
    passed = counts["passed"] == len(selected) and not any(
        counts[status] for status in ("failed", "error", "cancelled")
    )
    report = {
        "format": "reprolattice.suite-report.v1",
        "run_id": str(uuid.uuid4()),
        "suite": plan.name,
        "execution_context": {
            "python": platform.python_version(),
            "system": platform.system(),
            "machine": platform.machine(),
        },
        "suite_sha256": plan.snapshot_sha256,
        "definition_sha256": plan.definition_sha256,
        "started_at": started,
        "finished_at": utc_now(),
        "duration_seconds": time.monotonic() - wall_start,
        "jobs": jobs,
        "fail_fast": fail_fast,
        "selected_cases": len(selected),
        "total_cases": len(plan.cases),
        "full_suite": len(selected) == len(plan.cases),
        "selection": {
            "include_tags": list(include_tags),
            "exclude_tags": list(exclude_tags),
        },
        "passed": passed,
        "stop_reason": stop_reason,
        "counts": counts,
        "cases": ordered,
        "events": events,
        "workspace_policy": "fresh temporary directory per case; removed after the suite; trusted programs are not sandboxed",
    }
    return scrub(report, [secret for case in plan.cases for secret in case.secrets])
