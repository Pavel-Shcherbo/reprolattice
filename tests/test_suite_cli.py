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

