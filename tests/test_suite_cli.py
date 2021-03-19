import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from suite_fixtures import case, suite

ROOT = Path(__file__).resolve().parents[1]


class SuiteCliTests(unittest.TestCase):
    def test_packaged_example_runs_real_clients_and_writes_portable_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "reports"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "reprolattice.suites",
                    "examples/inventory-suite.json",
                    "--output",
                    str(output),
                    "--jobs",
                    "2",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((output / "report.json").read_text())
            self.assertEqual(report["counts"]["passed"], 5)
            self.assertTrue(report["full_suite"])
            self.assertEqual(
                len(
                    ET.parse(output / "junit.xml")
                    .getroot()
                    .find("testsuite")
                    .findall("testcase")
                ),
                5,
            )
            self.assertTrue((output / "manifest.json").is_file())

    def test_existing_output_is_rejected_before_starting_case(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "started"
            definition = suite(
                [
                    case(
                        command=[
                            sys.executable,
                            "-c",
                            f'open({str(marker)!r},"w").close()',
                        ]
                    )
                ]
            )
            spec = root / "suite.json"
            spec.write_text(json.dumps(definition))
            output = root / "reports"
            output.mkdir()
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "reprolattice.suites",
                    str(spec),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 2)
            self.assertFalse(marker.exists())
            self.assertEqual(list(output.iterdir()), [])

    @unittest.skipUnless(os.name == "posix", "POSIX interrupt and process cleanup")
    def test_interrupt_writes_cancelled_report_and_stops_application(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            started = root / "started"
            source = f"import os,time; from pathlib import Path; Path({str(started)!r}).write_text(str(os.getpid())); time.sleep(30)"
            definition = suite([case("slow", command=[sys.executable, "-c", source])])
            spec = root / "suite.json"
            spec.write_text(json.dumps(definition))
            output = root / "reports"
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "reprolattice.suites",
                    str(spec),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                deadline = time.monotonic() + 5
                while (
                    not started.exists()
                    and process.poll() is None
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.02)
                self.assertTrue(started.exists(), "case application never started")
                process.send_signal(signal.SIGINT)
                stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 130, stderr)
                report = json.loads((output / "report.json").read_text())
                self.assertEqual(report["counts"]["cancelled"], 1)
                self.assertFalse(report["passed"])
                with self.assertRaises(ProcessLookupError):
                    os.kill(int(started.read_text()), 0)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=3)
                if started.exists():
                    try:
                        os.killpg(int(started.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
