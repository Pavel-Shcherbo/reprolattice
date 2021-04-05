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

    def test_junit_counts_and_classification_match_the_run(self):
        xml = ET.fromstring(junit_xml(self.report))
        suite_node = xml.find("testsuite")
        self.assertEqual(suite_node.get("tests"), "3")
        self.assertEqual(suite_node.get("failures"), "1")
        self.assertEqual(suite_node.get("errors"), "1")
        self.assertIsNotNone(suite_node.findall("testcase")[1].find("failure"))
        self.assertIsNotNone(suite_node.findall("testcase")[2].find("error"))

    def test_html_and_xml_escape_untrusted_diagnostics(self):
        report = copy.deepcopy(self.report)
        report["cases"][2]["error"]["message"] = '<script>alert("x")</script> & \x00'
        html = html_report(report)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        xml = ET.fromstring(junit_xml(report))
        self.assertIn(
            "\ufffd",
            xml.find("testsuite").findall("testcase")[2].find("error").get("message"),
        )

