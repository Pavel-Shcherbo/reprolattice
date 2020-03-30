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

    def test_pointer_escapes_array_indices_and_root(self):
        document = {"a/b": {"~": [10, 20]}, "~1": "literal"}
        self.assertEqual(resolve(document, pointer_tokens("/a~1b/~0/1")), 20)
        self.assertEqual(resolve(document, pointer_tokens("/~01")), "literal")
        self.assertIs(resolve(document, pointer_tokens("/a~1b/~0/01")), MISSING)
        self.assertIs(resolve(document, pointer_tokens("/a~1b/~0/-")), MISSING)
        self.assertTrue(check(document, path="", op="type", value="object")["passed"])

    def test_numeric_comparisons_do_not_coerce_strings(self):
        for operation, expected in [("gt", 3), ("gte", 4), ("lt", 5), ("lte", 4)]:
            self.assertTrue(
                check({"n": 4}, path="/n", op=operation, value=expected)["passed"]
            )
            self.assertFalse(
                check({"n": "4"}, path="/n", op=operation, value=expected)["passed"]
            )
        self.assertFalse(check({"n": True}, path="/n", op="gte", value=0)["passed"])

    def test_integer_predicate_and_arbitrary_precision_equality(self):
        for value in [1, 1.0, 10**400]:
            self.assertTrue(check(value, op="type", value="integer")["passed"])
        for value in [True, 1.5, "1"]:
            self.assertFalse(check(value, op="type", value="integer")["passed"])
        self.assertTrue(check(10**400, op="gt", value=10**399)["passed"])

    def test_tolerance_is_explicit_and_avoids_float_overflow(self):
        self.assertTrue(
            check({"n": 1.001}, path="/n", op="approx", value=1, atol=0.002, rtol=0)[
                "passed"
            ]
        )
        self.assertFalse(
            check({"n": 1.01}, path="/n", op="approx", value=1, atol=0.002, rtol=0)[
                "passed"
            ]
        )
        self.assertFalse(
            check(-1e308, op="approx", value=1e308, atol=0, rtol=1.9)["passed"]
        )
        self.assertTrue(
            check(-1e308, op="approx", value=1e308, atol=0, rtol=2)["passed"]
        )

