"""Durable queue laboratory state, fencing, replay and independent worker effects."""

import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import http.client
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from reprolattice.queue_engine import QueueEngine
from reprolattice.queue_lab import QueueLab, verify_export
from reprolattice.queue_model import fingerprint, canonical
from reprolattice.queue_controls import run_worker_control, verify_worker_control
from reprolattice.queue_web import evaluate_queue


def config():
    return {
        "version": 1,
        "name": "orders",
        "visibility_seconds": 5,
        "max_deliveries": 2,
        "messages": [{"id": "order-42", "body": {"units": 4}}],
    }


def rehash(value):
    value["sha256"] = fingerprint({k: v for k, v in value.items() if k != "sha256"})


class QueueLabTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "queue.sqlite"
        self.lab = QueueLab(self.path)
        self.created = self.lab.apply(
            "one",
            "create",
            "create",
            {"label": "Order redelivery", "configuration": config()},
        )
        self.record = self.created["session"]["id"]

    def apply(self, key, commands, generation=None):
        if generation is None:
            generation = self.lab.view("one", self.record)["session"]["generation"]
        return self.lab.apply(
            "one",
            key,
            "commands",
            {"record": self.record, "generation": generation, "commands": commands},
        )

    def receive(self):
        return self.apply("receive", [{"operation": "receive", "owner": "worker-a"}])

    def test_real_redelivery_stale_ack_and_new_ack_have_independent_generations(self):
        first = self.receive()
        old = first["responses"][0]["body"]["message"]["delivery"]
        self.apply("expire", [{"operation": "advance", "seconds": 5}])
        second = self.apply("second", [{"operation": "receive", "owner": "worker-b"}])
        new = second["responses"][0]["body"]["message"]["delivery"]
        self.assertNotEqual(old, new)
        result = self.apply(
            "finish",
            [
                {"operation": "ack", "owner": "worker-a", "delivery": old},
                {"operation": "ack", "owner": "worker-b", "delivery": new},
            ],
        )
        self.assertEqual([r["status"] for r in result["responses"]], [400, 200])
        view = self.lab.view("one", self.record)
        self.assertEqual(
            view["state"]["counts"],
            {"queued": 0, "leased": 0, "acknowledged": 1, "dead": 0},
        )
        self.assertEqual(view["session"]["generation"], 5)
        self.assertEqual(view["state"]["rejected_commands"], 1)

