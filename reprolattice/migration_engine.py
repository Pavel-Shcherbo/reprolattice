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

