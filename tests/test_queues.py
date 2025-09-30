"""Independent delivery oracles, real crashed workers, wire failures and CI integration."""

import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import http.client
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from reprolattice.queue_model import configuration, fingerprint, fixture_contract
from reprolattice.queue_engine import QueueEngine, QueueCapacity, verify_queue_evidence
from reprolattice.queue_http import make_queue_server
from reprolattice.queue_harness import check_queue
from reprolattice.queues import write_evidence
from reprolattice.run_contract import validate_run
from reprolattice.run_registry import RunRegistry
from reprolattice.suite_config import compile_suite
from reprolattice.suite_runner import run_suite
from reprolattice.reports import write_reports

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load(name):
    return json.loads((EXAMPLES / name).read_bytes())


def definition(**changes):
    return {**load("queue-orders.json")["queue"], **changes}


def resign(document):
    document["sha256"] = fingerprint(
        {k: v for k, v in document.items() if k != "sha256"}
    )
    return document


class QueueEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = QueueEngine(definition())

    def op(self, operation, expected=200, **fields):
        value = self.engine.execute({"operation": operation, **fields})
        self.assertEqual(value["status"], expected, value)
        return value["body"]

    def receive(self, owner="one"):
        return self.op("receive", owner=owner)["message"]

