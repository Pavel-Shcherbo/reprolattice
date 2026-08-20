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

    def test_retry_after_restart_returns_original_delivery_without_another_receive(
        self,
    ):
        first = self.receive()
        self.lab = QueueLab(self.path)
        self.assertEqual(
            first,
            self.apply("receive", [{"operation": "receive", "owner": "worker-a"}], 1),
        )
        self.assertEqual(self.lab.view("one", self.record)["state"]["deliveries"], 1)
        self.assertEqual(self.lab.receipt("one", "receive"), first)

    def test_changed_request_binding_rejected_even_when_generation_would_match(self):
        self.receive()
        with self.assertRaisesRegex(ValueError, "different inputs"):
            self.apply("receive", [{"operation": "receive", "owner": "changed"}], 1)
        self.assertEqual(self.lab.view("one", self.record)["state"]["deliveries"], 1)

    def test_concurrent_same_request_is_one_delivery_and_one_generation(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            values = list(
                pool.map(
                    lambda _: self.apply(
                        "simultaneous", [{"operation": "receive", "owner": "a"}], 1
                    ),
                    range(4),
                )
            )
        self.assertTrue(all(v == values[0] for v in values))
        self.assertEqual(self.lab.view("one", self.record)["session"]["generation"], 2)
        self.assertEqual(self.lab.view("one", self.record)["state"]["deliveries"], 1)

    def test_concurrent_different_generation_requests_only_one_commits(self):
        def attempt(key):
            try:
                return self.apply(key, [{"operation": "receive", "owner": key}], 1)
            except ValueError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, ["a", "b"]))
        self.assertEqual(sum(v is not None for v in results), 1)
        self.assertEqual(self.lab.view("one", self.record)["session"]["generation"], 2)

    def test_capacity_failure_rolls_back_entire_batch_and_receipt(self):
        value = config()
        value["max_commands"] = 1
        created = self.lab.apply(
            "one", "small", "create", {"label": "Bounded", "configuration": value}
        )["session"]["id"]
        with self.assertRaisesRegex(ValueError, "quota"):
            self.lab.apply(
                "one",
                "too-many",
                "commands",
                {
                    "record": created,
                    "generation": 1,
                    "commands": [
                        {"operation": "receive", "owner": "a"},
                        {"operation": "advance", "seconds": 1},
                    ],
                },
            )
        view = self.lab.view("one", created)
        self.assertEqual(view["session"]["generation"], 1)
        self.assertEqual(view["commands"]["items"], [])
        with self.assertRaisesRegex(ValueError, "not found"):
            self.lab.receipt("one", "too-many")

    def test_failure_after_document_save_does_not_commit_document_without_receipt(self):
        original = self.lab.budget
        calls = 0

        def reject(db, extra=0):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError("simulated response failure")
            return original(db, extra)

        with (
            patch.object(self.lab, "budget", side_effect=reject),
            self.assertRaisesRegex(ValueError, "simulated"),
        ):
            self.receive()
        self.assertEqual(self.lab.view("one", self.record)["session"]["generation"], 1)
        with self.assertRaisesRegex(ValueError, "not found"):
            self.lab.receipt("one", "receive")

    def test_project_scoping_applies_to_views_receipts_commands_forks_exports(self):
        for callback in [
            lambda: self.lab.view("other", self.record),
            lambda: self.lab.receipt("other", "create"),
            lambda: self.lab.export("other", self.record, 1),
            lambda: self.lab.apply(
                "other",
                "write",
                "commands",
                {
                    "record": self.record,
                    "generation": 1,
                    "commands": [{"operation": "status"}],
                },
            ),
            lambda: self.lab.apply(
                "other",
                "fork",
                "fork",
                {"record": self.record, "generation": 1, "label": "foreign"},
            ),
        ]:
            with self.assertRaisesRegex(ValueError, "not found"):
                callback()
        self.assertEqual(self.lab.list("other")["items"], [])

    def test_fork_retains_state_and_command_chain_but_does_not_mutate_parent(self):
        self.receive()
        fork = self.lab.apply(
            "one",
            "branch",
            "fork",
            {"record": self.record, "generation": 2, "label": "Branch"},
        )["session"]
        self.assertEqual(fork["parent"]["id"], self.record)
        self.lab.apply(
            "one",
            "branch-time",
            "commands",
            {
                "record": fork["id"],
                "generation": 1,
                "commands": [{"operation": "advance", "seconds": 5}],
            },
        )
        self.assertEqual(self.lab.view("one", fork["id"])["state"]["clock"], 5)
        self.assertEqual(self.lab.view("one", self.record)["state"]["clock"], 0)
        self.assertEqual(
            self.lab.view("one", self.record)["state"]["counts"]["leased"], 1
        )
        with self.assertRaisesRegex(ValueError, "generation changed"):
            self.lab.apply(
                "one",
                "old-fork",
                "fork",
                {"record": self.record, "generation": 1, "label": "Stale"},
            )

    def test_imported_history_is_read_only_but_complete_history_can_be_forked(self):
        proof = QueueEngine(config()).evidence()
        record = self.lab.apply(
            "one", "imported", "import", {"label": "Imported", "evidence": proof}
        )["session"]["id"]
        with self.assertRaisesRegex(ValueError, "only authored"):
            self.lab.apply(
                "one",
                "edit-import",
                "commands",
                {
                    "record": record,
                    "generation": 1,
                    "commands": [{"operation": "status"}],
                },
            )
        fork = self.lab.apply(
            "one",
            "fork-import",
            "fork",
            {"record": record, "generation": 1, "label": "Authored continuation"},
        )["session"]
        self.assertEqual(fork["kind"], "simulation")

