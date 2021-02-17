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

