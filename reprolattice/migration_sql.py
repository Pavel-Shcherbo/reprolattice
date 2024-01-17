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

    def __call__(self, action, left, right, database, origin):
        decision = sqlite3.SQLITE_DENY
        protected = lambda value: isinstance(
            value, str
        ) and value.casefold().startswith(PREFIX)
        if action == sqlite3.SQLITE_ALTER_TABLE:
            if left == "main" and not protected(right):
                self.alter = True
                decision = sqlite3.SQLITE_OK
        elif action in DDL:
            if database == "main" and not protected(left) and not protected(right):
                decision = sqlite3.SQLITE_OK
        elif action in DML:
            if database == "main" and not protected(left):
                decision = sqlite3.SQLITE_OK
            elif (
                self.alter
                and database == "temp"
                and left in ("sqlite_temp_master", "sqlite_temp_schema")
            ):
                decision = sqlite3.SQLITE_OK
        elif action in (
            sqlite3.SQLITE_SELECT,
            getattr(sqlite3, "SQLITE_RECURSIVE", -1),
        ):
            decision = sqlite3.SQLITE_OK
        elif action == sqlite3.SQLITE_FUNCTION and isinstance(right, str):
            if (
                right.lower() in FUNCTIONS | {"like", "glob"}
                or self.alter
                and right.lower() in ALTER_FUNCTIONS
            ):
                decision = sqlite3.SQLITE_OK
        if decision == sqlite3.SQLITE_DENY:
            self.denial = {
                "action": action,
                "object": left,
                "detail": right,
                "database": database,
            }
        return decision


@contextmanager
def writer(path, budget):
    file_budget(path)
    with closing(
        sqlite3.connect(path, timeout=0.1, isolation_level=None, cached_statements=0)
    ) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA temp_store=MEMORY")
        page_size = db.execute("PRAGMA page_size").fetchone()[0]
        db.execute("PRAGMA max_page_count=" + str(MAX_DATABASE // page_size))
        if hasattr(db, "enable_load_extension"):
            db.enable_load_extension(False)
        if hasattr(db, "setlimit"):
            for category, limit in [
                ("SQLITE_LIMIT_LENGTH", 262144),
                ("SQLITE_LIMIT_SQL_LENGTH", 65536),
                ("SQLITE_LIMIT_COLUMN", 128),
                ("SQLITE_LIMIT_EXPR_DEPTH", 100),
                ("SQLITE_LIMIT_VARIABLE_NUMBER", 1000),
                ("SQLITE_LIMIT_COMPOUND_SELECT", 20),
                ("SQLITE_LIMIT_TRIGGER_DEPTH", 20),
            ]:
                db.setlimit(getattr(sqlite3, category), limit)
        db.set_progress_handler(budget.progress, 1000)
        try:
            yield db
        finally:
            db.set_authorizer(None)
            db.set_progress_handler(None, 0)
            if db.in_transaction:
                db.rollback()


