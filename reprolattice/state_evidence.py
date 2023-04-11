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


