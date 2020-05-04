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

    def test_collects_both_streams_and_exit_status(self):
        result = self.run_code(
            'import sys; print("ready"); print("warning", file=sys.stderr); sys.exit(7)'
        )
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, "ready\n")
        self.assertEqual(result.stderr, "warning\n")
        self.assertFalse(result.timed_out)
        self.assertFalse(result.output_limited)

