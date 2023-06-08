"""Retain actual suite snapshots and expose bounded archive inspection views."""

from .sqlite_inspect import compare_snapshots
from .state_archive import StateArchive
from .state_diff import compare_rows, table_page
from .state_evidence import StateCollector
from .sqlite_seed import identity
from .suite_runner import run_suite


