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

    def test_unbounded_streams_are_stopped_and_collection_is_capped(self):
        for stream in ["stdout", "stderr"]:
            with self.subTest(stream=stream):
                result = self.run_code(
                    f'import os;\nwhile True: os.write({1 if stream == "stdout" else 2}, b"x" * 65536)',
                    stdout_limit=2048,
                    stderr_limit=4096,
                )
                self.assertTrue(result.output_limited)
                self.assertLessEqual(len(result.stdout), 2048)
                self.assertLessEqual(len(result.stderr), 4096)
                self.assertIsNotNone(result.returncode)

    def test_invalid_utf8_is_reported(self):
        result = self.run_code('import os; os.write(1, b"\\xff")')
        self.assertFalse(result.stdout_valid_utf8)

    def test_timeout_stops_silent_process(self):
        result = self.run_code("import time; time.sleep(30)", timeout=0.1)
        self.assertTrue(result.timed_out)
        self.assertIsNotNone(result.returncode)

    @unittest.skipUnless(os.name == "posix", "POSIX process group semantics")
    def test_descendant_cannot_keep_pipes_open_after_parent_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "leaked"
            child = f'import time; time.sleep(0.8); open({str(marker)!r}, "w").close()'
            source = f'import subprocess,sys; subprocess.Popen([sys.executable,"-c",{child!r}])'
            started = time.monotonic()
            result = self.run_code(source, timeout=0.15)
            self.assertTrue(result.timed_out)
            self.assertLess(time.monotonic() - started, 1.5)
            time.sleep(0.8)
            self.assertFalse(marker.exists())

