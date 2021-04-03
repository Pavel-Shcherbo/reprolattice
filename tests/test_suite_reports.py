import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from reprolattice.reports import html_report, junit_xml, write_reports
from reprolattice.suite_config import compile_suite
from reprolattice.suite_runner import run_suite
from suite_fixtures import case, suite


class SuiteReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = run_suite(
            compile_suite(
                suite(
                    [
                        case("pass"),
                        case("fail", expected=False),
                        case("error", command=["/missing-program"]),
                    ]
                )
            )
        )

