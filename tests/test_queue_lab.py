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

