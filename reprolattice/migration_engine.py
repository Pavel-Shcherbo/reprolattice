"""Transactional migration/reversal checks over an explicitly isolated working copy."""

import copy
import sqlite3

from .migration_history import STACK, append_history, history, initialize_history
from .migration_model import MigrationPlan, compact_checks
from .migration_sql import execute_statement, writer
from .migration_state import app_snapshot
from .sqlite_inspect import Budget, check_queries, reader
from .sqlite_seed import identity


class MigrationDatabase:
    def __init__(self, path, plan, snapshots, *, initialize=False):
        if (
            not isinstance(plan, MigrationPlan)
            or identity(plan.definition) != plan.sha256
        ):
            raise ValueError("migration plan was mutated after compilation")
        self.path = path
        self.plan = MigrationPlan(copy.deepcopy(plan.definition), plan.sha256)
        self.snapshots = snapshots
        if initialize:
            with writer(path, Budget(2)) as db:
                db.execute("BEGIN IMMEDIATE")
                initialize_history(db)
                db.commit()

    def _snapshot(self, db, budget, diagnostic=False):
        value = app_snapshot(db, budget, diagnostic=diagnostic)
        self.snapshots.put(value)
        return value

    def step(self, index, direction, *, should_cancel=None):
        if (
            type(index) is not int
            or not 0 <= index < len(self.plan.definition["migrations"])
            or direction not in ("up", "down")
        ):
            raise ValueError(
                "migration step requires a declared index and up/down direction"
            )
        step = self.plan.definition["migrations"][index]
        budget = Budget(5, should_cancel)
        result = {
            "migration": step["id"],
            "direction": direction,
            "status": "failed",
            "before": None,
            "candidate": None,
            "after": None,
            "statements": [],
            "preconditions": None,
            "postconditions": None,
            "rollback_verified": False,
            "error": None,
            "diagnostic_error": None,
            "failure_stage": None,
            "failed_statement": None,
            "candidate_in_transaction": None,
        }
        with writer(self.path, Budget(2)) as db:
            db.execute("BEGIN IMMEDIATE")
            before = self._snapshot(db, Budget(2))
            result["before"] = before["sha256"]
            stack, events, _ = history(db, self.plan)
            db.set_progress_handler(budget.progress, 1000)
            stage = "ordering"
            statement_id = None
            try:
                budget.check()
                if direction == "up" and index < len(stack):
                    result.update(
                        status="already_applied",
                        candidate=before["sha256"],
                        after=before["sha256"],
                    )
                    db.rollback()
                    return result
                if direction == "down" and index >= len(stack):
                    result.update(
                        status="already_absent",
                        candidate=before["sha256"],
                        after=before["sha256"],
                    )
                    db.rollback()
                    return result
                if (
                    direction == "up"
                    and index != len(stack)
                    or direction == "down"
                    and index != len(stack) - 1
                ):
                    raise ValueError(
                        "migration must follow the applied prefix and reverse its current head"
                    )
                stage = "preconditions"
                checks = (
                    step["before_checks"] if direction == "up" else step["after_checks"]
                )
                result["preconditions"] = compact_checks(
                    check_queries(None, checks, _view=(db, budget))
                )
                if not result["preconditions"]["passed"]:
                    raise ValueError("migration preconditions failed")
                stage = "statements"
                for statement in step[direction]:
                    statement_id = statement["id"]
                    result["statements"].append(
                        execute_statement(db, budget, statement)
                    )
                statement_id = None
                stage = "postconditions"
                history(db, self.plan)
                if not db.in_transaction:
                    raise ValueError("migration ended the runner-owned transaction")
                db.set_authorizer(None)
                result["postconditions"] = compact_checks(
                    check_queries(
                        None,
                        (
                            step["after_checks"]
                            if direction == "up"
                            else step["rollback_checks"]
                        ),
                        _view=(db, budget),
                    )
                )
                if not result["postconditions"]["passed"]:
                    raise ValueError("migration postconditions failed")
                after = self._snapshot(db, budget)
                result["candidate"] = after["sha256"]
                stage = "restoration"
                if direction == "up":
                    item = {
                        "position": index + 1,
                        "migration": step["id"],
                        "step_sha256": identity(step),
                        "before_sha256": before["sha256"],
                        "after_sha256": after["sha256"],
                    }
                    append_history(db, self.plan, "up", item)
                    db.execute(
                        "INSERT INTO " + STACK + " VALUES(?,?,?,?,?)",
                        tuple(item.values()),
                    )
                else:
                    item = stack[-1]
                    if after["sha256"] != item["before_sha256"]:
                        raise ValueError(
                            "reverse SQL did not restore the exact original schema and rows"
                        )
                    append_history(db, self.plan, "down", item)
                    db.execute(
                        "DELETE FROM " + STACK + " WHERE position=?", (index + 1,)
                    )
                history(db, self.plan)
                budget.check()
                stage = "commit"
                db.commit()
                result.update(
                    status="applied" if direction == "up" else "reverted",
                    after=after["sha256"],
                )
            except (ValueError, sqlite3.Error) as error:
                result["failure_stage"] = stage
                result["failed_statement"] = statement_id
                result["candidate_in_transaction"] = db.in_transaction
                result["status"] = (
                    "cancelled" if budget.reason == "cancelled" else "failed"
                )
                result["error"] = (
                    ("migration " + budget.reason)
                    if budget.reason
                    else str(error)[:2048]
                )
                db.set_authorizer(None)
                db.set_progress_handler(None, 0)
                diagnostic = Budget(2)
                try:
                    db.set_progress_handler(diagnostic.progress, 1000)
                    if result["candidate"] is None:
                        result["candidate"] = self._snapshot(db, diagnostic, True)[
                            "sha256"
                        ]
                except (ValueError, sqlite3.Error) as problem:
                    result["diagnostic_error"] = str(problem)[:2048]
                finally:
                    db.set_progress_handler(None, 0)
                    if db.in_transaction:
                        db.rollback()
                try:
                    cleanup = Budget(2)
                    db.set_progress_handler(cleanup.progress, 1000)
                    restored = self._snapshot(db, cleanup)
                    result["after"] = restored["sha256"]
                    result["rollback_verified"] = restored["sha256"] == before["sha256"]
                except (ValueError, sqlite3.Error) as problem:
                    result["diagnostic_error"] = str(problem)[:2048]
        return result

