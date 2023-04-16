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


