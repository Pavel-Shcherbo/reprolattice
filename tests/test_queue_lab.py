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

    def test_portable_saved_export_import_uses_new_project_and_read_only_history(self):
        self.receive()
        value = self.lab.export("one", self.record, 2)
        record = self.lab.apply(
            "two", "restored", "import", {"label": "Restored", "evidence": value}
        )["session"]
        self.assertNotEqual(record["id"], self.record)
        self.assertEqual(record["kind"], "imported")
        self.assertEqual(record["project"], "two")
        self.assertEqual(record["parent"]["id"], self.record)
        self.assertEqual(
            self.lab.view("two", record["id"])["state"],
            self.lab.view("one", self.record)["state"],
        )

    def test_incomplete_import_stays_explicit_and_cannot_be_forked(self):
        proof = QueueEngine(config()).evidence(wire_errors=1)
        record = self.lab.apply(
            "one", "incomplete", "import", {"label": "Incomplete", "evidence": proof}
        )["session"]["id"]
        self.assertFalse(self.lab.view("one", record)["complete"])
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.lab.apply(
                "one",
                "bad-fork",
                "fork",
                {"record": record, "generation": 1, "label": "Cannot continue"},
            )
        self.assertFalse(
            verify_export(self.lab.export("one", record, 1))["replay"]["complete"]
        )

    def test_corrupt_queue_hash_and_rehashed_impossible_state_rejected(self):
        for rehashed in [False, True]:
            proof = QueueEngine(config()).evidence()
            proof["state"]["clock"] = 5
            if rehashed:
                rehash(proof)
            with self.subTest(rehashed=rehashed), self.assertRaises(ValueError):
                self.lab.apply(
                    "one",
                    "bad" + str(rehashed),
                    "import",
                    {"label": "Bad", "evidence": proof},
                )

    def test_receipt_and_stored_document_corruption_are_detected(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(
                "UPDATE receipts SET response_sha='bad' WHERE request_key='create'"
            )
            db.commit()
        with self.assertRaisesRegex(ValueError, "receipt identity"):
            self.lab.receipt("one", "create")
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute(
                "select document from sessions where id=?", (self.record,)
            ).fetchone()
            value = json.loads(row[0])
            value["state"]["clock"] = 1
            db.execute(
                "update sessions set document=? where id=?",
                (canonical(value), self.record),
            )
            db.commit()
        with self.assertRaisesRegex(ValueError, "content identity"):
            self.lab.view("one", self.record)

    def test_newest_first_list_and_message_command_pagination(self):
        value = config()
        value["messages"] = [{"id": f"item-{i}", "body": i} for i in range(30)]
        record = self.lab.apply(
            "one", "many", "create", {"label": "Many", "configuration": value}
        )["session"]["id"]
        for i in range(2):
            self.lab.apply(
                "one",
                "advance" + str(i),
                "commands",
                {
                    "record": record,
                    "generation": i + 1,
                    "commands": [{"operation": "advance", "seconds": 1}] * 20,
                },
            )
        first = self.lab.view("one", record)
        last = self.lab.view("one", record, generation=3, message_offset=25, after=25)
        self.assertEqual(len(first["messages"]["items"]), 25)
        self.assertEqual(len(last["messages"]["items"]), 5)
        self.assertEqual(
            [e["sequence"] for e in last["commands"]["items"]], list(range(26, 41))
        )
        listing = self.lab.list("one", limit=1)
        self.assertEqual(listing["items"][0]["id"], record)
        self.assertEqual(
            self.lab.list("one", before=listing["next_cursor"], limit=1)["items"][0][
                "id"
            ],
            self.record,
        )
        with self.assertRaisesRegex(ValueError, "generation changed"):
            self.lab.view("one", record, generation=2, after=25)

    def test_export_offline_without_database_preserves_json_numbers(self):
        value = config()
        value["messages"][0]["body"] = {"value": 1.0}
        record = self.lab.apply(
            "one",
            "float",
            "create",
            {"label": "Numeric payload", "configuration": value},
        )["session"]["id"]
        export = self.lab.export("one", record, 1)
        serialized = canonical(export).decode()
        outer = json.loads(json.dumps({"content": serialized}))
        self.path.unlink()
        self.assertIn("1.0", outer["content"])
        self.assertTrue(verify_export(json.loads(outer["content"]))["passed"])

    def test_retained_quota_rejects_new_sessions_without_partial_rows(self):
        with (
            patch("reprolattice.queue_lab.MAX_SESSIONS", 1),
            self.assertRaisesRegex(ValueError, "quota"),
        ):
            self.lab.apply(
                "one",
                "overflow",
                "create",
                {"label": "Overflow", "configuration": config()},
            )
        self.assertEqual(len(self.lab.list("one")["items"]), 1)
        with (
            patch("reprolattice.queue_lab.MAX_RETAINED", 1),
            self.assertRaisesRegex(ValueError, "quota"),
        ):
            self.receive()

    def test_bad_fields_and_batch_shape_cannot_mutate_state(self):
        for commands in [[], {}, [{}] * 51]:
            with self.assertRaises(ValueError):
                self.apply("bad" + str(type(commands)), commands)
        for generation in [0, True, "1"]:
            with self.assertRaises(ValueError):
                self.apply("bad-generation", [{"operation": "status"}], generation)
        with self.assertRaises(ValueError):
            self.lab.apply(
                "one",
                "path",
                "create",
                {"label": "Bad", "configuration": config(), "path": "/tmp/unwanted"},
            )
        self.assertEqual(self.lab.view("one", self.record)["session"]["generation"], 1)

    def test_killed_process_cannot_leave_delivery_without_retry_receipt(self):
        script = """
import os,sys
from reprolattice.queue_lab import QueueLab
lab=QueueLab(sys.argv[1])
original=lab.save
def die(*args,**kwargs):
 original(*args,**kwargs)
 os._exit(17)
lab.save=die
lab.apply('one','killed','commands',{'record':sys.argv[2],'generation':1,'commands':[{'operation':'receive','owner':'a'}]})
"""
        process = subprocess.run(
            [sys.executable, "-c", script, str(self.path), self.record],
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(process.returncode, 17, process.stderr)
        self.assertEqual(self.lab.view("one", self.record)["session"]["generation"], 1)
        with self.assertRaisesRegex(ValueError, "not found"):
            self.lab.receipt("one", "killed")
        value = self.apply("killed", [{"operation": "receive", "owner": "a"}], 1)
        self.assertEqual(value["responses"][0]["body"]["message"]["attempt"], 1)

    def test_session_metadata_identity_and_unrelated_database_guard(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("UPDATE sessions SET metadata_sha='bad'")
            db.commit()
        with self.assertRaisesRegex(ValueError, "metadata"):
            self.lab.list("one")
        unrelated = Path(self.temporary.name) / "unrelated.sqlite"
        with closing(sqlite3.connect(unrelated)) as db:
            db.execute("create table foreign_data(value)")
            db.commit()
        with self.assertRaisesRegex(ValueError, "unrelated"):
            QueueLab(unrelated)


class QueueWorkerControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.control = run_worker_control()

    def test_real_worker_observations_reconcile_without_confusing_protocol_and_effects(
        self,
    ):
        proof = verify_worker_control(self.control)
        self.assertEqual(
            proof["inventory_by_behavior"], {"idempotent": 6, "duplicate": 2}
        )
        self.assertTrue(proof["protocol_histories_equal"])
        self.assertFalse(proof["observed_suite_passed"])
        self.assertFalse(proof["application_reexecuted"])

    def test_rehashed_snapshot_change_cannot_qualify_duplicate_effect(self):
        value = copy.deepcopy(self.control)
        case = next(
            c
            for c in value["report"]["cases"]
            if c["parameters"]["behavior"] == "duplicate"
        )
        value["states"][case["id"]]["after"]["tables"]["inventory"]["rows"][0][
            "available"
        ]["value"] = 6
        rehash(value)
        with self.assertRaises(ValueError):
            verify_worker_control(value)

    def test_worker_save_retry_does_not_launch_another_process_and_allows_case_fork(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            lab = QueueLab(Path(temporary) / "queues.sqlite")
            with patch(
                "reprolattice.queue_lab.run_worker_control", return_value=self.control
            ) as runner:
                result = lab.apply("one", "workers", "workers", {"label": "Workers"})
                self.assertEqual(
                    result, lab.apply("one", "workers", "workers", {"label": "Workers"})
                )
                self.assertEqual(runner.call_count, 1)
            record = result["session"]["id"]
            view = lab.view("one", record)
            self.assertEqual(len(view["cases"]), 2)
            fork = lab.apply(
                "one",
                "fork",
                "fork",
                {
                    "label": "Worker continuation",
                    "record": record,
                    "generation": 1,
                    "case": view["selected_case"],
                },
            )
            self.assertEqual(
                lab.view("one", fork["session"]["id"])["state"], view["state"]
            )
            self.assertTrue(verify_export(lab.export("one", record, 1))["passed"])

    def test_web_fields_and_overview_are_scoped_without_database_creation(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch(
                "reprolattice.queue_web.state_directory", return_value=Path(temporary)
            ),
        ):
            self.assertEqual(
                evaluate_queue({"mode": "queue", "action": "overview"})["items"], []
            )
            self.assertFalse(
                (Path(temporary) / "queue-workbench/queues.sqlite").exists()
            )
            with self.assertRaises(ValueError):
                evaluate_queue(
                    {"mode": "queue", "action": "overview", "path": "/tmp/elsewhere"}
                )
            created = evaluate_queue(
                {
                    "mode": "queue",
                    "action": "create",
                    "request_key": "new",
                    "payload": {"label": "Web queue", "configuration": config()},
                }
            )
            exported = evaluate_queue(
                {
                    "mode": "queue",
                    "action": "export",
                    "record": created["session"]["id"],
                    "generation": 1,
                }
            )
            self.assertTrue(verify_export(json.loads(exported["content"]))["passed"])


class QueueLabHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        with closing(socket.socket()) as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        env = {**os.environ, "REPROLATTICE_STATE_DIR": cls.temp.name}
        cls.process = subprocess.Popen(
            [sys.executable, "-m", "reprolattice.web", "--port", str(cls.port)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        for _ in range(100):
            try:
                connection = http.client.HTTPConnection(
                    "127.0.0.1", cls.port, timeout=1
                )
                connection.request("GET", "/health")
                r = connection.getresponse()
                r.read()
                connection.close()
                if r.status == 200:
                    return
            except OSError:
                time.sleep(0.02)
        cls.process.terminate()
        raise RuntimeError("queue HTTP server did not start")

