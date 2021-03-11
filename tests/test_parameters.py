import unittest

from reprolattice.parameters import expand, variants, scrub


class ParameterTests(unittest.TestCase):
    def test_matrix_order_is_deterministic_and_typed(self):
        values = variants({"size": [1, 2], "enabled": [True, False]})
        self.assertEqual(
            values,
            [
                {"enabled": True, "size": 1},
                {"enabled": True, "size": 2},
                {"enabled": False, "size": 1},
                {"enabled": False, "size": 2},
            ],
        )
        self.assertEqual(
            expand(
                {"quantity": {"$param": "size"}, "path": "/item/${size}"}, values[0]
            ),
            {"quantity": 1, "path": "/item/1"},
        )
        self.assertEqual(expand("${enabled}", values[0]), "true")

    def test_typed_values_are_copied_and_string_interpolation_is_not_a_shell(self):
        parameters = {"value": {"nested": [True]}, "text": "$(touch never-created)"}
        result = expand({"$param": "value"}, parameters)
        result["nested"].append(False)
        self.assertEqual(parameters["value"], {"nested": [True]})
        self.assertEqual(expand("${text}", parameters), parameters["text"])
        with self.assertRaises(ValueError):
            expand("prefix ${value}", parameters)

