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


