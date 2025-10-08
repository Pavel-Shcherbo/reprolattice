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

    def test_visibility_boundary_redelivery_and_stale_ack_fence(self):
        first = self.receive()
        self.assertEqual((first["attempt"], first["lease_until"]), (1, 5))
        self.assertIsNone(self.receive("two"))
        self.op("advance", seconds=4)
        self.assertIsNone(self.receive("two"))
        self.op("advance", seconds=1)
        second = self.receive("two")
        self.assertEqual((second["id"], second["attempt"]), ("order-42", 2))
        self.op("ack", expected=400, owner="one", delivery=first["delivery"])
        self.assertEqual(self.engine.snapshot()["counts"]["leased"], 1)
        self.op("ack", owner="two", delivery=second["delivery"])
        self.assertEqual(self.engine.snapshot()["counts"]["acknowledged"], 1)
        self.assertTrue(verify_queue_evidence(self.engine.evidence())["complete"])

    def test_same_ack_receipt_is_observational_and_wrong_owner_or_operation_fails(self):
        message = self.receive()
        self.op("ack", expected=400, owner="other", delivery=message["delivery"])
        original = self.op("ack", owner="one", delivery=message["delivery"])
        self.op("advance", seconds=20)
        repeated = self.op("ack", owner="one", delivery=message["delivery"])
        self.assertEqual(
            {k: v for k, v in original.items() if k != "reused"},
            {k: v for k, v in repeated.items() if k != "reused"},
        )
        self.assertTrue(repeated["reused"])
        self.op("nack", expected=400, owner="one", delivery=message["delivery"])
        self.assertEqual(self.engine.snapshot()["counts"]["acknowledged"], 1)

    def test_delayed_nack_retries_and_exact_delivery_limit(self):
        first = self.receive()
        self.op("nack", owner="one", delivery=first["delivery"], delay_seconds=7)
        self.assertTrue(
            self.op("nack", owner="one", delivery=first["delivery"], delay_seconds=7)[
                "reused"
            ]
        )
        self.op(
            "nack",
            expected=400,
            owner="one",
            delivery=first["delivery"],
            delay_seconds=8,
        )
        self.op("advance", seconds=6)
        self.assertIsNone(self.receive())
        self.op("advance", seconds=1)
        second = self.receive("two")
        self.op("nack", owner="two", delivery=second["delivery"])
        self.assertIsNone(self.receive())
        state = self.engine.snapshot()
        self.assertEqual((state["deliveries"], state["counts"]["dead"]), (2, 1))

    def test_final_visibility_expiry_moves_to_dead_letter_without_an_extra_delivery(
        self,
    ):
        first = self.receive()
        self.op("advance", seconds=5)
        second = self.receive("two")
        self.op("advance", seconds=5)
        self.assertIsNone(self.receive("three"))
        self.op("ack", expected=400, owner="two", delivery=second["delivery"])
        self.assertEqual(self.engine.snapshot()["counts"]["dead"], 1)
        self.assertEqual(self.engine.deliveries, 2)

