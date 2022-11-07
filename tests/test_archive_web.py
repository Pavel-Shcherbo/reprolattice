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

