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
    pass
