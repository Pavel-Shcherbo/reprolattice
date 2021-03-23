import copy
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

from reprolattice.suite_config import compile_suite
from suite_fixtures import case, fixture, suite


class SuiteConfigurationTests(unittest.TestCase):
    def test_all_parameter_variants_are_preflighted(self):
        definition = suite()
        definition["cases"][0]["matrix"] = {"ok": [True, 1]}
        definition["cases"][0]["fixture"]["application"]["expected_json"] = {
            "ok": {"$param": "ok"}
        }
        plan = compile_suite(definition)
        self.assertEqual(len(plan.cases), 2)
        self.assertIs(plan.cases[0].fixture["application"]["expected_json"]["ok"], True)
        self.assertEqual(plan.cases[1].fixture["application"]["expected_json"]["ok"], 1)
        self.assertNotEqual(plan.cases[0].id, plan.cases[1].id)

