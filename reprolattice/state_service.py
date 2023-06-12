"""Retain actual suite snapshots and expose bounded archive inspection views."""

from .sqlite_inspect import compare_snapshots
from .state_archive import StateArchive
from .state_diff import compare_rows, table_page
from .state_evidence import StateCollector
from .sqlite_seed import identity
from .suite_runner import run_suite


def execute_retained(plan, archive, project, *, request_key, label="", jobs=2):
    request_fingerprint = identity(
        {
            "suite": plan.snapshot_sha256,
            "jobs": jobs,
            "retention": "reprolattice.state-evidence.v1",
        }
    )
    previous = archive.requested(project, request_key, request_fingerprint, label)
    if previous is not None:
        return {"record": previous["record"], "report": previous["document"]["report"]}
    collector = StateCollector(plan)
    report = run_suite(plan, jobs=jobs, on_state=collector)
    document = collector.finish(report)
    record = archive.record(
        project,
        document,
        request_key=request_key,
        label=label,
        request_fingerprint=request_fingerprint,
    )
    return {"record": record, "report": report}


