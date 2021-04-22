import unittest
from xml.etree import ElementTree as ET

from reprolattice.web import evaluate


class SuiteWorkbenchTests(unittest.TestCase):
    def test_reviewed_suite_and_faulty_client_have_distinct_outcomes(self):
        healthy = evaluate({"mode": "suite", "jobs": 2})
        self.assertTrue(healthy["report"]["passed"])
        self.assertEqual(healthy["report"]["counts"]["passed"], 5)
        self.assertEqual(
            ET.fromstring(healthy["junit_xml"]).find("testsuite").get("failures"), "0"
        )
        faulty = evaluate({"mode": "suite", "faulty_client": True})
        self.assertFalse(faulty["report"]["passed"])
        self.assertEqual(faulty["report"]["counts"]["failed"], 3)
        self.assertEqual(faulty["report"]["counts"]["passed"], 2)
        self.assertEqual(
            ET.fromstring(faulty["junit_xml"]).find("testsuite").get("failures"), "3"
        )

    def test_workbench_does_not_accept_arbitrary_commands_or_suites(self):
        for params in [
            {"mode": "suite", "command": ["arbitrary"]},
            {"mode": "suite", "suite": {}},
            {"mode": "suite", "jobs": True},
            {"mode": "suite", "faulty_client": "yes"},
        ]:
            with self.subTest(params=params), self.assertRaises(ValueError):
                evaluate(params)
