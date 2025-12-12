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


