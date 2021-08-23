"""Structured, constrained SQLite fixtures published without overwriting files."""

import copy
import hashlib
import json
import math
import os
import re
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from .jsonutil import validate_json

NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
TYPES = {"INTEGER", "REAL", "TEXT", "BLOB"}
MAX_DATABASE = 16 * 1024 * 1024


