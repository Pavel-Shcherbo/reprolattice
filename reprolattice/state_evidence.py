"""Opt-in bounded SQLite snapshot retention tied to actual suite checks."""

import copy
import threading

from .jsonutil import validate_json
from .redaction import secret_key
from .run_contract import validate_run, sha
from .sqlite_inspect import compare_snapshots, verify_database_snapshot
from .sqlite_seed import canonical, identity
from .suite_config import relative_path

FORMAT = "reprolattice.state-evidence.v1"
MAX_EVIDENCE = 32 * 1024 * 1024
MAX_PAIR = 2 * 1024 * 1024


def ensure_retainable(plan):
    for case in plan.cases:
        if case.secrets:
            raise ValueError(
                "raw state retention is unavailable for secret-parameter cases"
            )
        for state in case.states:
            for table in state.seed["tables"]:
                for column in table["columns"]:
                    if secret_key(column["name"]):
                        raise ValueError(
                            "raw state retention refuses named sensitive columns"
                        )


def safe_snapshot(snapshot):
    verify_database_snapshot(snapshot)
    for name, table in snapshot["tables"].items():
        if secret_key(name) or any(
            secret_key(column["name"]) for column in table["columns"]
        ):
            raise ValueError(
                "raw state retention refuses named sensitive tables/columns"
            )


class StateCollector:
    def __init__(self, plan):
        ensure_retainable(plan)
        self.pairs = []
        self.bytes = 0
        self.lock = threading.Lock()

    def __call__(self, case, state, before, after):
        safe_snapshot(before)
        safe_snapshot(after)
        pair = {
            "case": case.id,
            "path": state.path,
            "definition_sha256": state.sha256,
            "before": before,
            "after": after,
        }
        size = len(canonical(pair))
        if size > MAX_PAIR:
            raise ValueError("state snapshot pair exceeds 2 MiB retention limit")
        with self.lock:
            if self.bytes + size > 24 * 1024 * 1024 or len(self.pairs) >= 1024:
                raise ValueError("retained state collection exceeds its run budget")
            self.pairs.append(copy.deepcopy(pair))
            self.bytes += size

    def finish(self, report):
        result = {
            "format": FORMAT,
            "report": copy.deepcopy(report),
            "pairs": sorted(self.pairs, key=lambda row: (row["case"], row["path"])),
        }
        result["sha256"] = identity(result)
        validate_evidence(result)
        return result


