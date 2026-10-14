"""Restore internal SQL access across the supported SQLite Python bindings."""

import sqlite3
import sys


def clear_authorizer(db):
    """Leave the query-only/transaction guards intact; callers install SQL policy."""
    if sys.version_info >= (3, 11):
        db.set_authorizer(None)
    else:
        # Disabling the callback with None is supported only from Python 3.11.
        db.set_authorizer(lambda *_: sqlite3.SQLITE_OK)
