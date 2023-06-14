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


def inspect_record(archive, project, record):
    stored = archive.get(project, record)
    value = stored["document"]
    cases = {case["id"]: case for case in value["report"]["cases"]}
    pairs = []
    for pair in value["pairs"]:
        before, after = pair["before"], pair["after"]
        checks = next(
            item
            for item in cases[pair["case"]]["sqlite"]
            if item["path"] == pair["path"]
        )
        pairs.append(
            {
                "case": pair["case"],
                "path": pair["path"],
                "case_status": cases[pair["case"]]["status"],
                "parameters": cases[pair["case"]]["parameters"],
                "checks": checks.get("checks"),
                "definition_sha256": pair["definition_sha256"],
                "before_sha256": before["sha256"],
                "after_sha256": after["sha256"],
                "changes": compare_snapshots(before, after),
                "schema": {"before": before["schema"], "after": after["schema"]},
                "tables": [
                    {
                        "name": name,
                        "before_rows": len(
                            before["tables"].get(name, {}).get("rows", [])
                        ),
                        "after_rows": len(
                            after["tables"].get(name, {}).get("rows", [])
                        ),
                    }
                    for name in sorted(set(before["tables"]) | set(after["tables"]))
                ],
            }
        )
    return {
        "record": stored["record"],
        "pairs": pairs,
        "run_counts": value["report"]["counts"],
        "source_authenticated": False,
    }


