"""Author, inspect and export saved queue histories from the local command line."""

import argparse
import json
from pathlib import Path
import sqlite3

from .jsonutil import strict_json
from .queue_lab import QueueLab, MAX_DOCUMENT, verify_export
from .queue_model import canonical


def load(path):
    with Path(path).open("rb") as stream:
        return strict_json(
            stream.read(MAX_DOCUMENT + 1), max_bytes=MAX_DOCUMENT, max_nodes=4000000
        )


