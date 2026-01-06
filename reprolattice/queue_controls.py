"""Reviewed crash workers and separately retained typed database observations."""

import json

from .queue_engine import verify_queue_evidence
from .queue_model import canonical, fields, fingerprint
from .resources import examples_directory
from .run_contract import validate_run
from .sqlite_inspect import verify_database_snapshot
from .suite_config import compile_suite
from .suite_runner import run_suite

FORMAT = "reprolattice.queue-worker-control.v1"


def run_worker_control():
    root = examples_directory()
    definition = json.loads((root / "queue-effects-suite.json").read_text())
    proofs, states = {}, {}

    def queue(case, evidence):
        proofs[case.id] = evidence

    def state(case, specification, before, after):
        states[case.id] = {"before": before, "after": after}

    report = run_suite(
        compile_suite(definition, root), jobs=2, on_queue=queue, on_state=state
    )
    result = {"format": FORMAT, "report": report, "proofs": proofs, "states": states}
    result["sha256"] = fingerprint(result)
    verify_worker_control(result)
    return result


def verify_worker_control(value):
    fields(value, ("format", "report", "proofs", "states", "sha256"))
    if value["format"] != FORMAT or value["sha256"] != fingerprint(
        {k: v for k, v in value.items() if k != "sha256"}
    ):
        raise ValueError("worker control content identity differs")
    report = value["report"]
    validate_run(report)
    cases = report["cases"]
    if (
        len(cases) != 2
        or set(value["proofs"]) != {c["id"] for c in cases}
        or set(value["states"]) != set(value["proofs"])
    ):
        raise ValueError("worker control requires two complete queue/database cases")
    observed = {}
    proofs = []
    for case in cases:
        behavior = case["parameters"].get("behavior")
        if behavior not in ("idempotent", "duplicate") or behavior in observed:
            raise ValueError("worker control behavior differs")
        evidence = value["proofs"][case["id"]]
        replay = verify_queue_evidence(evidence)
        summary = case["detail"].get("queue_evidence_summary", {})
        if (
            not replay["complete"]
            or summary.get("sha256") != evidence["sha256"]
            or summary.get("commands") != len(evidence["journal"])
            or summary.get("complete") is not True
        ):
            raise ValueError("worker case lacks matching complete queue history")
        if not case["detail"]["passed"] or not all(case["detail"]["checks"].values()):
            raise ValueError(
                "reviewed worker protocol/application output control did not pass"
            )
        pair = value["states"][case["id"]]
        fields(pair, ("before", "after"))
        for snapshot in pair.values():
            verify_database_snapshot(snapshot)
        if len(case["sqlite"]) != 1:
            raise ValueError("worker control requires one observed SQLite database")
        check = case["sqlite"][0]
        if (
            check["before_sha256"] != pair["before"]["sha256"]
            or check["after_sha256"] != pair["after"]["sha256"]
        ):
            raise ValueError("worker database report differs from retained snapshots")
        before = pair["before"]["tables"]["inventory"]["rows"]
        after = pair["after"]["tables"]["inventory"]["rows"]
        expected_before = [
            {
                "part": {"type": "text", "value": "part-42"},
                "available": {"type": "integer", "value": 10},
            }
        ]
        stock = 6 if behavior == "idempotent" else 2
        expected_after = [
            {
                "part": {"type": "text", "value": "part-42"},
                "available": {"type": "integer", "value": stock},
            }
        ]
        receipt = [
            {
                "job": {"type": "text", "value": "order-42"},
                "units": {"type": "integer", "value": 4},
            }
        ]
        if (
            before != expected_before
            or after != expected_after
            or pair["before"]["tables"]["processed"]["rows"] != []
            or pair["after"]["tables"]["processed"]["rows"] != receipt
        ):
            raise ValueError(
                "worker inventory/receipt observations disagree with independent control"
            )
        queries = {q["id"]: q for q in check["checks"]["queries"]}
        if (
            set(queries) != {"inventory_effect_once", "one_receipt"}
            or queries["inventory_effect_once"]["actual"] != after
            or queries["one_receipt"]["actual"] != receipt
        ):
            raise ValueError(
                "worker assertion observations differ from SQLite snapshots"
            )
        passed = behavior == "idempotent"
        if (
            case["status"] != ("passed" if passed else "failed")
            or check["passed"] is not passed
            or check["checks"]["passed"] is not passed
            or queries["inventory_effect_once"]["passed"] is not passed
            or queries["one_receipt"]["passed"] is not True
        ):
            raise ValueError(
                "worker failure classification differs from observed effect"
            )
        observed[behavior] = stock
        proofs.append(evidence)
    if canonical(proofs[0]) != canonical(proofs[1]) or report["passed"] is not False:
        raise ValueError(
            "reviewed workers require equal broker histories and one failed effect"
        )
    return {
        "passed": True,
        "inventory_by_behavior": observed,
        "protocol_histories_equal": True,
        "observed_suite_passed": False,
        "application_reexecuted": False,
        "source_authenticated": False,
    }
