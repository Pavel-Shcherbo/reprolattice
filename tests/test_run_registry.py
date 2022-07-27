"""Archive immutability, baseline fencing and independently classified regressions."""

import copy
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

from reprolattice.run_contract import fingerprint, validate_run
from reprolattice.run_compare import comparison
from reprolattice.run_registry import RunRegistry
from reprolattice.suite_config import compile_suite
from reprolattice.suite_runner import run_suite

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
CONTEXT = {"runner": "controlled-test"}


