import fnmatch
import http.client
import itertools
import json
import threading
import unittest

from reprolattice.matching import compile_request, glob_match
from reprolattice.replay import make_server


class MatchingTests(unittest.TestCase):
    def test_small_globs_match_an_independent_standard_library_oracle(self):
        patterns = [
            "".join(value)
            for length in range(4)
            for value in itertools.product("ab*?", repeat=length)
        ]
        texts = [
            "".join(value)
            for length in range(5)
            for value in itertools.product("ab", repeat=length)
        ]
        for pattern in patterns:
            for value in texts:
                self.assertEqual(
                    glob_match(pattern, value),
                    fnmatch.fnmatchcase(value, pattern),
                    (pattern, value),
                )
        self.assertFalse(glob_match("*", "x" * 8193))

