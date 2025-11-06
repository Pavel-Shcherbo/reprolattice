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

    def test_delayed_seed_and_publish_order_follow_readiness_then_insertion(self):
        self.engine = QueueEngine(
            definition(
                messages=[
                    {"id": "later", "body": {}, "delay_seconds": 5},
                    {"id": "ready", "body": {}},
                ]
            )
        )
        first = self.receive()
        self.assertEqual(first["id"], "ready")
        self.op("ack", owner="one", delivery=first["delivery"])
        self.assertIsNone(self.receive())
        self.op("advance", seconds=5)
        self.assertEqual(self.receive()["id"], "later")

    def test_publication_idempotency_conflicts_and_no_terminal_requeue(self):
        value = {"id": "new", "body": {"units": 2}, "request_key": "publish"}
        self.assertFalse(self.op("publish", **value)["reused"])
        self.op("publish", expected=400, **{**value, "body": {"units": 3}})
        self.op("publish", expected=400, **{**value, "request_key": "another"})
        self.assertTrue(self.op("publish", **value)["reused"])
        for _ in range(2):
            item = self.receive()
            self.op("ack", owner="one", delivery=item["delivery"])
        self.assertTrue(self.op("publish", **value)["reused"])
        self.assertIsNone(self.receive())
        self.assertEqual(self.engine.snapshot()["message_count"], 2)

    def test_concurrent_receivers_never_own_the_same_attempt(self):
        self.engine = QueueEngine(
            definition(messages=[{"id": f"m-{n}", "body": {"n": n}} for n in range(20)])
        )

        def receive(n):
            return self.engine.execute({"operation": "receive", "owner": f"w-{n}"})[
                "body"
            ]["message"]

        with ThreadPoolExecutor(max_workers=8) as pool:
            values = list(pool.map(receive, range(30)))
        received = [item for item in values if item]
        self.assertEqual(len(received), 20)
        self.assertEqual(len({item["id"] for item in received}), 20)
        self.assertEqual(len({item["delivery"] for item in received}), 20)
        self.assertEqual(self.engine.snapshot()["counts"]["leased"], 20)
        self.assertTrue(verify_queue_evidence(self.engine.evidence())["passed"])

    def test_capacity_and_invalid_clock_do_not_partially_mutate_messages(self):
        self.engine = QueueEngine(definition(max_messages=1))
        self.op("publish", expected=400, id="overflow", body={}, request_key="overflow")
        for seconds in (-1, True, 0.5, 86401):
            self.op("advance", expected=400, seconds=seconds)
        self.assertEqual(self.engine.clock, 0)
        self.assertEqual(len(self.engine.messages), 1)
        self.assertEqual(self.engine.messages["order-42"]["attempts"], 0)

    def test_command_budget_marks_incomplete_without_an_unjournaled_ack(self):
        self.engine = QueueEngine(definition(max_commands=1))
        item = self.receive()
        with self.assertRaises(QueueCapacity):
            self.engine.execute(
                {"operation": "ack", "owner": "one", "delivery": item["delivery"]}
            )
        self.assertEqual(self.engine.snapshot()["counts"]["leased"], 1)
        value = self.engine.evidence()
        self.assertEqual(value["dropped_commands"], 1)
        self.assertFalse(verify_queue_evidence(value)["complete"])

    def test_combined_byte_budget_preserves_a_verifiable_prefix(self):
        self.engine = QueueEngine(
            definition(
                messages=[
                    {"id": f"m-{n}", "body": {"value": "x" * 8000}} for n in range(100)
                ]
            )
        )
        with self.assertRaises(QueueCapacity):
            for _ in range(10):
                self.engine.execute({"operation": "status"})
        proof = verify_queue_evidence(self.engine.evidence())
        self.assertTrue(proof["passed"])
        self.assertFalse(proof["complete"])
        self.assertEqual(proof["message_count"], 100)

    def test_caller_mutation_cannot_change_retained_state_or_journal(self):
        item = self.receive()
        item["body"]["units"] = 999
        snapshot = self.engine.snapshot()
        snapshot["messages"][0]["body"]["units"] = 999
        exported = self.engine.evidence()
        exported["journal"].clear()
        exported["configuration"]["max_deliveries"] = 20
        self.assertEqual(self.engine.configuration["max_deliveries"], 2)
        self.assertEqual(self.engine.messages["order-42"]["body"]["units"], 4)
        self.assertEqual(len(self.engine.journal), 1)
        self.assertTrue(verify_queue_evidence(self.engine.evidence())["passed"])

    def test_rehashed_forgery_of_response_state_or_chain_is_rejected(self):
        self.receive()
        original = self.engine.evidence()
        malformed = copy.deepcopy(original)
        malformed["journal"] = [{}]
        with self.assertRaises(ValueError):
            verify_queue_evidence(resign(malformed))
        for field in ("response", "state", "chain"):
            value = copy.deepcopy(original)
            if field == "response":
                value["journal"][0]["response"]["body"]["message"]["attempt"] = 2
            elif field == "state":
                value["state"]["messages"][0]["body"]["units"] = 999
            else:
                value["journal"][0]["previous_sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                verify_queue_evidence(resign(value))

    def test_configuration_and_command_preflight_are_strict(self):
        for change in (
            {"version": True},
            {"max_deliveries": 0},
            {"visibility_seconds": True},
            {"messages": [{"id": "x", "body": {}}, {"id": "x", "body": {}}]},
        ):
            with self.assertRaises(ValueError):
                configuration(definition(**change))
        self.op("ack", expected=400, owner="one", delivery="unknown")
        self.op("receive", expected=400, owner="one", extra=True)
        with self.assertRaises(ValueError):
            self.engine.execute({"value": float("nan")})
        self.assertFalse(self.engine.evidence()["complete"])


class QueueWireTests(unittest.TestCase):
    def setUp(self):
        self.server, self.engine, self.token, self.wire = make_queue_server(
            definition()
        )
        self.thread = threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=0.01), daemon=True
        )
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(
        self, value=None, *, headers=None, path="/command", method="POST", raw=None
    ):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=4
        )
        self.addCleanup(connection.close)
        head = {"Content-Type": "application/json", "X-Queue-Fixture": self.token}
        if headers:
            head.update(headers)
        connection.request(
            method, path, raw if raw is not None else json.dumps(value), head
        )
        response = connection.getresponse()
        payload = response.read()
        return response.status, json.loads(payload) if payload else None

    def test_valid_commands_are_journaled_but_capability_is_not_exported(self):
        status, value = self.request({"operation": "receive", "owner": "worker"})
        self.assertEqual(status, 200)
        self.assertEqual(value["message"]["attempt"], 1)
        self.assertNotIn(self.token, json.dumps(self.engine.evidence()))
        self.assertTrue(
            verify_queue_evidence(
                self.engine.evidence(wire_errors=self.wire["errors"])
            )["complete"]
        )

    def test_foreign_host_origin_and_non_ascii_capability_are_counted(self):
        for headers in (
            {"Host": "outside.example"},
            {"Origin": "https://outside.example"},
            {"X-Queue-Fixture": "wrong"},
            {"X-Queue-Fixture": "é"},
        ):
            self.assertEqual(
                self.request({"operation": "status"}, headers=headers)[0], 403
            )
        self.assertEqual(self.wire["errors"], 4)
        self.assertFalse(
            self.engine.evidence(wire_errors=self.wire["errors"])["complete"]
        )

    def test_bad_wire_and_unsupported_methods_cannot_look_complete(self):
        self.assertEqual(
            self.request(raw='{"operation":"status","operation":"advance"}')[0], 400
        )
        self.assertEqual(self.request(raw="NaN")[0], 400)
        self.assertEqual(self.request({}, path="/outside")[0], 404)
        self.assertEqual(self.request({}, method="TRACE")[0], 501)
        self.assertEqual(self.request({}, method="GET")[0], 405)
        self.assertEqual(self.wire["errors"], 5)
        self.assertEqual(len(self.engine.journal), 0)

    def wait_until_accepted(self):
        deadline = time.monotonic() + 1
        while self.wire["accepted"] == 0 and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertEqual(self.wire["accepted"], 1)

    def test_partial_connection_has_a_total_deadline_before_shutdown(self):
        connection = socket.create_connection(
            ("127.0.0.1", self.server.server_port), timeout=3
        )
        stop = threading.Event()

        def drip():
            for _ in range(12):
                if stop.wait(0.25):
                    return
                try:
                    connection.sendall(b"x")
                except OSError:
                    return

        thread = threading.Thread(target=drip, daemon=True)
        try:
            connection.sendall(b"POST /command HTTP/1.1\r\n")
            self.wait_until_accepted()
            thread.start()
            started = time.monotonic()
            self.server.shutdown()
            self.assertLess(time.monotonic() - started, 3.5)
            self.assertGreaterEqual(self.wire["errors"], 1)
        finally:
            stop.set()
            connection.close()
            if thread.ident is not None:
                thread.join(timeout=1)

    def test_oversized_content_length_rejected_before_reading(self):
        self.assertEqual(self.request({}, headers={"Content-Length": "131073"})[0], 400)
        self.assertEqual(self.wire["errors"], 1)

    def test_incomplete_headers_close_without_hanging_fixture_shutdown(self):
        connection = socket.create_connection(
            ("127.0.0.1", self.server.server_port), timeout=3
        )
        connection.sendall(b"POST /command HTTP/1.1\r\n")
        self.wait_until_accepted()
        started = time.monotonic()
        connection.close()
        self.server.shutdown()
        self.assertLess(time.monotonic() - started, 3)
        self.assertGreaterEqual(self.wire["errors"], 1)


class QueueHarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = load("queue-orders.json")

    def test_actual_crashed_worker_and_independently_read_sqlite_effect(self):
        result = check_queue(
            self.fixture,
            [sys.executable, str(EXAMPLES / "queue_worker.py")],
            cwd=self.root,
        )
        self.assertTrue(result["passed"], result)
        with closing(sqlite3.connect(self.root / "queue-effects.sqlite")) as db:
            self.assertEqual(
                db.execute("SELECT available FROM inventory").fetchone()[0], 6
            )
            self.assertEqual(
                db.execute("SELECT job,units FROM processed").fetchall(),
                [("order-42", 4)],
            )
        self.assertEqual(
            (result["queue"]["deliveries"], result["queue"]["rejected_commands"]),
            (5, 1),
        )
        self.assertEqual(
            result["queue_evidence"]["state"]["counts"],
            {"queued": 0, "leased": 0, "acknowledged": 2, "dead": 1},
        )

    def test_queue_protocol_alone_does_not_prove_exactly_once_side_effect(self):
        result = check_queue(
            self.fixture,
            [
                sys.executable,
                str(EXAMPLES / "queue_worker.py"),
                "--behavior",
                "duplicate",
            ],
            cwd=self.root,
        )
        self.assertTrue(result["passed"])
        with closing(sqlite3.connect(self.root / "queue-effects.sqlite")) as db:
            self.assertEqual(
                db.execute("SELECT available FROM inventory").fetchone()[0], 2
            )

