"""Bounded single-statement write SQL, with runner-owned transaction control."""

from contextlib import closing, contextmanager
import sqlite3

from .migration_model import PREFIX
from .sqlite_inspect import Budget, FUNCTIONS, file_budget
from .sqlite_seed import MAX_DATABASE, sqlite_value

DDL = frozenset(
    getattr(sqlite3, name)
    for name in (
        "SQLITE_CREATE_TABLE",
        "SQLITE_CREATE_INDEX",
        "SQLITE_DROP_TABLE",
        "SQLITE_DROP_INDEX",
        "SQLITE_CREATE_VIEW",
        "SQLITE_DROP_VIEW",
        "SQLITE_CREATE_TRIGGER",
        "SQLITE_DROP_TRIGGER",
    )
)
DML = frozenset(
    (
        sqlite3.SQLITE_INSERT,
        sqlite3.SQLITE_UPDATE,
        sqlite3.SQLITE_DELETE,
        sqlite3.SQLITE_READ,
    )
)
ALTER_FUNCTIONS = frozenset(
    "sqlite_rename_table sqlite_rename_column sqlite_rename_test sqlite_rename_quotefix sqlite_drop_column".split()
)


class WriteAuthorizer:
    def __init__(self):
        self.alter = False
        self.denial = None

