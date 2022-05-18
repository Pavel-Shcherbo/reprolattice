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


def save_comparison(result, path):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".run-comparison-", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(
                (json.dumps(result, indent=2, allow_nan=False) + "\n").encode()
            )
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


