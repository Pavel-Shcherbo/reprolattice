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

