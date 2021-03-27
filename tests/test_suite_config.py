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

    def test_inputs_are_snapshotted_and_hash_pins_are_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "client.py"
            source.write_text('print("initial")')
            definition = suite()
            definition["cases"][0]["files"] = [
                {
                    "path": "client.py",
                    "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                }
            ]
            plan = compile_suite(definition, directory)
            source.write_text("changed")
            self.assertEqual(plan.cases[0].files[0].content, b'print("initial")')
            with self.assertRaisesRegex(ValueError, "pinned"):
                compile_suite(definition, directory)

    def test_invalid_future_case_prevents_any_process_start(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "started"
            definition = suite(
                [
                    case(
                        "side-effect",
                        command=[
                            sys.executable,
                            "-c",
                            f'open({str(marker)!r},"w").close()',
                        ],
                    ),
                    case("invalid"),
                ]
            )
            definition["cases"][1]["fixture"]["application"]["assertions"] = [
                {"op": "typo", "value": 1}
            ]
            with self.assertRaises(ValueError):
                compile_suite(definition, directory)
            self.assertFalse(marker.exists())

    def test_paths_cannot_escape_or_overlap(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            tempfile.TemporaryDirectory() as outside,
        ):
            (Path(directory) / "outside").symlink_to(outside, target_is_directory=True)
            for path in ["../client.py", "/tmp/client.py", "outside/client.py"]:
                definition = suite()
                definition["cases"][0]["files"] = [{"path": path}]
                with self.subTest(path=path), self.assertRaises(ValueError):
                    compile_suite(definition, directory)

    def test_unknown_fields_duplicate_ids_and_invalid_tags_are_rejected(self):
        invalid = [suite([case(), case()]), suite()]
        invalid[1]["cases"][0]["tags"] = [{}]
        for definition in invalid:
            with self.assertRaises(ValueError):
                compile_suite(definition)
        definition = suite()
        definition["cases"][0]["fixture"]["application"]["expectd_json"] = {}
        with self.assertRaisesRegex(ValueError, "unsupported"):
            compile_suite(definition)

    def test_protocol_sample_is_validated_without_starting_server(self):
        definition = suite(
            [
                {
                    "id": "protocol",
                    "mode": "protocol",
                    "fixture": {
                        "interactions": [
                            {
                                "request": {
                                    "method": "GET",
                                    "path_pattern": "/items/*",
                                },
                                "response": {"json": {}},
                            }
                        ]
                    },
                }
            ]
        )
        with self.assertRaisesRegex(ValueError, "sample_request"):
            compile_suite(definition)

