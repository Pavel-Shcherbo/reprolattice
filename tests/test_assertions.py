import json
import math
import unittest

from reprolattice.assertions import (
    compile_rules,
    evaluate_rules,
    json_equal,
    pointer_tokens,
    resolve,
    MISSING,
)
from reprolattice.jsonutil import strict_json, validate_json


def check(actual, **rule):
    return evaluate_rules(actual, compile_rules([rule]))[0]


class AssertionTests(unittest.TestCase):
    def test_json_boolean_and_number_are_distinct(self):
        self.assertFalse(json_equal(True, 1))
        self.assertFalse(json_equal({"flag": True}, {"flag": 1}))
        self.assertTrue(json_equal(1, 1.0))
        self.assertFalse(
            check({"flag": 1}, path="/flag", op="equals", value=True)["passed"]
        )

    def test_missing_null_and_empty_key_remain_distinct(self):
        document = {"null": None, "": 5}
        self.assertTrue(check(document, path="/null", op="exists")["passed"])
        self.assertTrue(check(document, path="/missing", op="absent")["passed"])
        self.assertFalse(
            check(document, path="/missing", op="equals", value=None)["passed"]
        )
        self.assertFalse(
            check(document, path="/missing", op="not_equals", value=7)["passed"]
        )
        self.assertTrue(check(document, path="/", op="equals", value=5)["passed"])

