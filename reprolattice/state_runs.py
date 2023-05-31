"""Opt-in retention and inspection of trusted local suites' SQLite states."""

import argparse
import json
from pathlib import Path
import sqlite3

from .jsonutil import strict_json
from .state_archive import StateArchive
from .state_service import execute_retained, inspect_record, inspect_table, inspect_diff
from .suite_config import compile_suite


