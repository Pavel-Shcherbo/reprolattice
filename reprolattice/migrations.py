"""Qualify reversible SQLite migrations on isolated copies and replay evidence."""

import argparse
import json
from pathlib import Path
import sqlite3

from .jsonutil import strict_json
from .migration_bundle import verify_migration_bundle
from .migration_runner import qualify_migrations


