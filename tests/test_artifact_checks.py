import json
import tempfile
import unittest
from pathlib import Path

from reprolattice.artifact_checks import check_artifacts
from reprolattice.suite_config import compile_artifacts


class ArtifactCheckTests(unittest.TestCase):
    def test_missing_malformed_and_wrong_type_outputs_are_failures(self):
        definition = compile_artifacts(
            [
                {
                    "path": "output.json",
                    "kind": "json",
                    "assertions": [{"path": "/ok", "op": "equals", "value": True}],
                }
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(check_artifacts(directory, definition)[0]["passed"])
            path = Path(directory) / "output.json"
            path.write_text("{not-json}")
            self.assertIn("error", check_artifacts(directory, definition)[0])
            path.write_text('{"ok":1}')
            report = check_artifacts(directory, definition)[0]
            self.assertFalse(report["passed"])
            self.assertFalse(report["assertions"][0]["passed"])

    def test_symlink_cannot_import_external_output_into_report(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            tempfile.TemporaryDirectory() as outside,
        ):
            external = Path(outside) / "private.json"
            external.write_text('{"secret":"external-canary"}')
            (Path(directory) / "output.json").symlink_to(external)
            report = check_artifacts(
                directory, compile_artifacts([{"path": "output.json", "kind": "json"}])
            )
            self.assertFalse(report[0]["passed"])
            self.assertIn("symlink", report[0]["error"])
            self.assertNotIn("external-canary", json.dumps(report))

    def test_text_and_hash_assertions_are_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "output.txt").write_text("ready\n")
            definitions = compile_artifacts(
                [
                    {
                        "path": "output.txt",
                        "kind": "text",
                        "assertions": [{"op": "contains", "value": "ready"}],
                        "sha256": "0" * 64,
                    }
                ]
            )
            report = check_artifacts(directory, definitions)[0]
            self.assertTrue(report["assertions"][0]["passed"])
            self.assertFalse(report["hash_passed"])
            self.assertFalse(report["passed"])
