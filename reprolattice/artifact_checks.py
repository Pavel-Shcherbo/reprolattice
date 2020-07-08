"""Inspect declared case outputs without copying arbitrary application files."""

import hashlib
from pathlib import Path

from .assertions import evaluate_rules
from .jsonutil import strict_json
from .suite_config import rooted, read_bounded


