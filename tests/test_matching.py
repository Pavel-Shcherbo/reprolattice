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

    def test_request_supports_variable_paths_headers_queries_and_json(self):
        matcher = compile_request(
            {
                "method": "POST",
                "path_pattern": "/orders/*",
                "headers": {"Content-Type": "application/json"},
                "json_assertions": [
                    {"path": "/amount", "op": "gte", "value": 1},
                    {"path": "/id", "op": "type", "value": "string"},
                ],
                "header_assertions": [{"path": "/x-request-id", "op": "exists"}],
                "query_assertions": [
                    {"path": "/mode", "op": "one_of", "value": ["draft", "live"]}
                ],
            }
        )
        self.assertEqual(
            matcher.match(
                "POST",
                "/orders/42?mode=draft",
                {"amount": 3, "id": "order-42"},
                {"content-type": "application/json", "X-Request-ID": "trace"},
            ),
            [],
        )
        issues = matcher.match(
            "POST",
            "/orders/42?mode=unknown",
            {"amount": False, "id": 3},
            {"Content-Type": "text/plain"},
        )
        self.assertEqual(
            {item["component"] for item in issues}, {"headers", "query", "json"}
        )

    def test_exact_paths_keep_query_encoding_and_header_duplicates_fail(self):
        matcher = compile_request(
            {"method": "GET", "path": "/search?q=a%20b", "headers": {"X-Trace": "one"}}
        )
        self.assertEqual(
            matcher.match("GET", "/search?q=a%20b", None, [("x-trace", "one")]), []
        )
        self.assertTrue(
            matcher.match("GET", "/search?q=a+b", None, [("x-trace", "one")])
        )
        self.assertTrue(
            matcher.match(
                "GET", "/search?q=a%20b", None, [("X-Trace", "one"), ("x-trace", "two")]
            )
        )

    def test_repeated_query_values_are_available_as_arrays(self):
        matcher = compile_request(
            {
                "method": "GET",
                "path": "/search",
                "query_assertions": [
                    {"path": "/tag", "op": "equals", "value": ["a", "b"]},
                    {"path": "/empty", "op": "equals", "value": ""},
                ],
            }
        )
        self.assertEqual(
            matcher.match("GET", "/search?tag=a&tag=b&empty=", None, {}), []
        )
        self.assertTrue(matcher.match("GET", "/search?tag=a", None, {}))

