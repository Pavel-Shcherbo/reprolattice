"""Archive local suite runs, control named baselines and explain comparison gates."""

import argparse
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from .jsonutil import strict_json
from .run_registry import RunRegistry
from .run_contract import fingerprint
from .suite_config import read_bounded


