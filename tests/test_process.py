import os
import signal
import sys
import tempfile
import time
import unittest
from pathlib import Path

from reprolattice.process import run_process


class ProcessTests(unittest.TestCase):
    def run_code(self, source, **options):
        return run_process(
            [sys.executable, "-c", source],
            env={"PATH": os.environ.get("PATH", "")},
            **options,
        )

