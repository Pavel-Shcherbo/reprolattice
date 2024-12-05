"""Retained rehearsal replay, scoped inspection, fenced recovery and UI controls."""

import copy
import concurrent.futures
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

from reprolattice.migration_archive import MigrationArchive
from reprolattice.migration_runner import qualify_migrations
from reprolattice.migration_views import (
    inspect_rehearsal,
    phase_table,
    export_rehearsal,
    verify_retained_migration,
)
from reprolattice.migration_web import control_inputs, evaluate_migrations
from reprolattice.sqlite_seed import identity


class MigrationArchiveTests(unittest.TestCase):
    pass
