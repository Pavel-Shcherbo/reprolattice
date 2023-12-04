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
    pass
