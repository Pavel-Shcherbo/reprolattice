"""Linearized virtual-clock deliveries, fenced acknowledgements and replay journal."""

import copy
import threading

from .jsonutil import validate_json
from .queue_model import (
    canonical,
    configuration,
    fields,
    fingerprint,
    integer,
    name,
    MAX_EVIDENCE,
)


class QueueCapacity(ValueError):
    pass


class QueueEngine:
    def __init__(self, definition):
        self.configuration = configuration(definition)
        self.clock = 0
        self.messages = {}
        self.publish_requests = {}
        self.tokens = {}
        self.sequence = 0
        self.deliveries = 0
        self.rejections = 0
        self.journal = []
        self.head = fingerprint({"configuration": self.configuration})
        self.journal_bytes = 0
        self.dropped_commands = 0
        self.lock = threading.RLock()
        for sequence, item in enumerate(self.configuration["messages"], 1):
            self.messages[item["id"]] = self.message(
                item["id"], item["body"], sequence, item.get("delay_seconds", 0)
            )
        self.sequence = len(self.messages)

    @staticmethod
    def message(identity, body, order, available_at):
        return {
            "id": identity,
            "body": copy.deepcopy(body),
            "order": order,
            "status": "queued",
            "available_at": available_at,
            "attempts": 0,
            "active_delivery": None,
            "lease_until": None,
            "owner": None,
        }

    def execute(self, command):
        try:
            validate_json(command, max_bytes=131072, max_depth=35, max_nodes=11000)
        except ValueError:
            with self.lock:
                self.dropped_commands += 1
            raise
        with self.lock:
            if len(self.journal) >= self.configuration["max_commands"]:
                self.dropped_commands += 1
                raise QueueCapacity("queue command quota exceeded")
            # Reserve the maximum possible entry before applying any command.
            # Quota rejection cannot leave an unjournaled mutation behind.
            if (
                self.journal_bytes
                + len(canonical(command))
                + self.configuration["max_body_bytes"]
                + 8192
                > 6 * 1024 * 1024
            ):
                self.dropped_commands += 1
                raise QueueCapacity("queue retained journal byte quota exceeded")
            state_bytes = len(canonical(self.snapshot()))
            response_budget = (
                state_bytes + 128
                if isinstance(command, dict) and command.get("operation") == "status"
                else self.configuration["max_body_bytes"] + 8192
            )
            if (
                len(canonical(self.configuration))
                + state_bytes
                + self.journal_bytes
                + len(canonical(command))
                + response_budget
                + self.configuration["max_body_bytes"]
                + 16384
                > MAX_EVIDENCE // 2
            ):
                self.dropped_commands += 1
                raise QueueCapacity("queue combined state/evidence byte quota exceeded")
            try:
                response = {"status": 200, "body": self.operate(command)}
            except ValueError as error:
                self.rejections += 1
                response = {"status": 400, "body": {"error": str(error)}}
            content = {
                "sequence": len(self.journal) + 1,
                "at": self.clock,
                "command": copy.deepcopy(command),
                "response": copy.deepcopy(response),
                "previous_sha256": self.head,
            }
            content["sha256"] = fingerprint(content)
            self.journal.append(content)
            self.head = content["sha256"]
            self.journal_bytes += len(canonical(content))
            return copy.deepcopy(response)

    def operate(self, command):
        if not isinstance(command, dict):
            raise ValueError("queue command requires an object")
        operation = command.get("operation")
        if operation == "publish":
            return self.publish(command)
        if operation == "receive":
            return self.receive(command)
        if operation in ("ack", "nack"):
            return self.finish(command)
        if operation == "advance":
            fields(command, ("operation", "seconds"))
            seconds = integer(command["seconds"], "clock advance", 0, 86400)
            if self.clock + seconds > 1000000000:
                raise ValueError("virtual queue clock exceeds its range")
            self.clock += seconds
            expired = []
            for message in sorted(
                self.messages.values(), key=lambda item: item["order"]
            ):
                if (
                    message["status"] == "leased"
                    and message["lease_until"] <= self.clock
                ):
                    delivery = message["active_delivery"]
                    self.tokens[delivery]["status"] = "expired"
                    self.release(message, 0)
                    expired.append(message["id"])
            return {"clock": self.clock, "expired": expired}
        if operation == "status":
            fields(command, ("operation",))
            return self.snapshot()
        raise ValueError("unsupported queue operation")

