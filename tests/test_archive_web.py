"""Saved suite evidence, strict browser requests and coherent baseline review."""

import copy
import json
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from reprolattice.archive_web import PROJECT
from reprolattice.run_contract import canonical, fingerprint
from reprolattice.run_registry import RunRegistry
from reprolattice.suite_web import evaluate_suite
from reprolattice.web import evaluate
from test_run_registry import report


class ArchiveWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.healthy = evaluate_suite({"mode": "suite", "jobs": 2})["report"]
        cls.faulty = evaluate_suite(
            {"mode": "suite", "jobs": 2, "faulty_client": True}
        )["report"]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "state"
        self.environment = patch.dict(
            "os.environ", {"REPROLATTICE_STATE_DIR": str(self.root)}
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def api(self, action, **fields):
        return evaluate({"mode": "archive", "action": action, **fields})

    def save(self, value=None, key="first", label="Reviewed control"):
        return self.api(
            "archive",
            report=copy.deepcopy(value or self.healthy),
            request_key=key,
            label=label,
        )["record"]

    def registry(self):
        return RunRegistry(self.root / "run-workbench/runs.sqlite")

    def test_empty_overview_and_invalid_requests_do_not_initialize_database(self):
        self.assertFalse(self.api("overview")["initialized"])
        self.assertFalse((self.root / "run-workbench/runs.sqlite").exists())
        bad = [
            {"action": "archive", "report": {}, "request_key": "bad"},
            {"action": "inspect", "record": "../../outside"},
            {"action": "overview", "after": True},
            {"action": "overview", "after": 2**64},
            {"action": "overview", "project": "other"},
            {"action": "history", "source": "case", "status": []},
            {
                "action": "move",
                "name": "accepted",
                "record": "a" * 64,
                "generation": 0,
                "reason": " ",
            },
            {
                "action": "compare",
                "record": "a" * 64,
                "before": "b" * 64,
                "baseline": "accepted",
            },
            {
                "action": "archive",
                "report": self.healthy,
                "request_key": "good",
                "command": ["bad"],
            },
        ]
        for request in bad:
            with (
                self.subTest(request=request.get("action")),
                self.assertRaises(ValueError),
            ):
                evaluate({"mode": "archive", **request})
        self.assertFalse((self.root / "run-workbench/runs.sqlite").exists())

