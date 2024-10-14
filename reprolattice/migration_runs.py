"""Retain local migration rehearsals and verify their portable archive envelopes."""

import argparse
import json
from pathlib import Path
import sqlite3

from .migration_archive import MigrationArchive
from .migration_views import (
    inspect_rehearsal,
    export_rehearsal,
    verify_retained_migration,
    MAX_EXPORT,
)
from .jsonutil import strict_json
from .migrations import load
from .sqlite_seed import canonical


