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

    def test_input_is_closed(self):
        result = self.run_code("import sys; print(repr(sys.stdin.read()))")
        self.assertEqual(result.stdout, "''\n")

    def test_exact_limit_is_accepted(self):
        result = self.run_code(
            'import sys; sys.stdout.write("x" * 1000)', stdout_limit=1000
        )
        self.assertEqual(len(result.stdout), 1000)
        self.assertFalse(result.output_limited)

