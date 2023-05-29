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


def validate_evidence(value):
    validate_json(value, max_bytes=MAX_EVIDENCE, max_depth=75, max_nodes=1800000)
    if (
        not isinstance(value, dict)
        or set(value) != {"format", "report", "pairs", "sha256"}
        or value["format"] != FORMAT
    ):
        raise ValueError("unsupported retained state evidence")
    if identity({key: item for key, item in value.items() if key != "sha256"}) != sha(
        value["sha256"]
    ):
        raise ValueError("retained state evidence identity mismatch")
    validate_run(value["report"])
    pairs = value["pairs"]
    if not isinstance(pairs, list) or len(pairs) > 1024:
        raise ValueError("retained evidence exceeds 1024 database pairs")
    cases = {case["id"]: case for case in value["report"]["cases"]}
    seen = set()
    for pair in pairs:
        if (
            not isinstance(pair, dict)
            or set(pair) != {"case", "path", "definition_sha256", "before", "after"}
            or not isinstance(pair["case"], str)
            or pair["case"] not in cases
        ):
            raise ValueError("snapshot pair requires a recorded case")
        key = (pair["case"], relative_path(pair["path"]))
        if key in seen or len(canonical(pair)) > MAX_PAIR:
            raise ValueError("duplicate or oversized state pair")
        seen.add(key)
        case = cases[pair["case"]]
        definitions = {
            item["path"]: item["sha256"] for item in case.get("sqlite_definitions", [])
        }
        states = [
            item for item in case.get("sqlite", []) if item["path"] == pair["path"]
        ]
        if len(states) != 1 or definitions.get(pair["path"]) != sha(
            pair["definition_sha256"]
        ):
            raise ValueError("snapshot pair does not match recorded state definition")
        state = states[0]
        for side in ("before", "after"):
            safe_snapshot(pair[side])
            if state.get(side + "_sha256") != pair[side]["sha256"]:
                raise ValueError("snapshot pair does not match recorded state identity")
        if state.get("changes") != compare_snapshots(pair["before"], pair["after"]):
            raise ValueError("snapshot differences contradict recorded state changes")
    if pairs != sorted(pairs, key=lambda row: (row["case"], row["path"])):
        raise ValueError("snapshot pairs require canonical ordering")
    return value


def evidence_summary(value):
    report = value["report"]
    retained = {(pair["case"], pair["path"]) for pair in value["pairs"]}
    expected = {
        (case["id"], state["path"])
        for case in report["cases"]
        for state in case.get("sqlite_definitions", [])
    }
    missing = sorted(expected - retained)
    return {
        "id": value["sha256"],
        "run_id": report["run_id"],
        "suite": report["suite"],
        "passed": report["passed"],
        "counts": report["counts"],
        "finished_at": report["finished_at"],
        "retained_pairs": len(retained),
        "expected_pairs": len(expected),
        "capture_complete": not missing,
        "missing_pairs": [{"case": case, "path": path} for case, path in missing],
        "source_authenticated": False,
    }


