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

    def publish(self, command):
        fields(command, ("operation", "id", "body", "request_key"), ("delay_seconds",))
        identity = name(command["id"], "message ID")
        request = name(command["request_key"], "publish request key")
        delay = integer(command.get("delay_seconds", 0), "publish delay", 0, 86400)
        validate_json(
            command["body"],
            max_bytes=self.configuration["max_body_bytes"],
            max_depth=30,
            max_nodes=10000,
        )
        binding = fingerprint(
            {"id": identity, "body": command["body"], "delay_seconds": delay}
        )
        prior = self.publish_requests.get(request)
        if prior:
            if prior["binding"] != binding:
                raise ValueError("publish request key identifies another message")
            return {"id": identity, "reused": True}
        if self.clock + delay > 1000000000:
            raise ValueError("publish delay exceeds the virtual clock range")
        if identity in self.messages:
            raise ValueError("message ID already exists under another request")
        if len(self.messages) >= self.configuration["max_messages"]:
            raise ValueError("queue message capacity exceeded")
        self.sequence += 1
        self.messages[identity] = self.message(
            identity, command["body"], self.sequence, self.clock + delay
        )
        self.publish_requests[request] = {"binding": binding, "id": identity}
        return {"id": identity, "reused": False}

    def receive(self, command):
        fields(command, ("operation", "owner"))
        owner = name(command["owner"], "delivery owner")
        candidates = sorted(
            (
                item
                for item in self.messages.values()
                if item["status"] == "queued" and item["available_at"] <= self.clock
            ),
            key=lambda item: (item["available_at"], item["order"]),
        )
        if not candidates:
            return {"message": None, "clock": self.clock}
        message = candidates[0]
        if self.clock + self.configuration["visibility_seconds"] > 1000000000:
            raise ValueError("delivery lease exceeds the virtual clock range")
        attempt = message["attempts"] + 1
        token = fingerprint(
            [
                self.configuration["name"],
                message["id"],
                attempt,
                len(self.journal) + 1,
                owner,
            ]
        )
        self.deliveries += 1
        message.update(
            status="leased",
            attempts=attempt,
            active_delivery=token,
            owner=owner,
            lease_until=self.clock + self.configuration["visibility_seconds"],
        )
        self.tokens[token] = {
            "message": message["id"],
            "owner": owner,
            "attempt": attempt,
            "status": "leased",
            "receipt": None,
            "finish_binding": None,
        }
        return {
            "message": {
                "id": message["id"],
                "body": copy.deepcopy(message["body"]),
                "attempt": attempt,
                "delivery": token,
                "lease_until": message["lease_until"],
            },
            "clock": self.clock,
        }

    def finish(self, command):
        operation = command["operation"]
        fields(
            command,
            ("operation", "delivery", "owner"),
            ("delay_seconds",) if operation == "nack" else (),
        )
        token = command["delivery"]
        if not isinstance(token, str) or len(token) != 64:
            raise ValueError("delivery requires its exact token")
        owner = name(command["owner"], "delivery owner")
        delay = integer(command.get("delay_seconds", 0), "retry delay", 0, 86400)
        binding = fingerprint(
            {"operation": operation, "owner": owner, "delay_seconds": delay}
        )
        prior = self.tokens.get(token)
        if prior is None or prior["owner"] != owner:
            raise ValueError("unknown delivery or mismatched owner")
        if prior["receipt"] is not None:
            if prior["finish_binding"] != binding:
                raise ValueError("delivery already finished with another operation")
            return {**prior["receipt"], "reused": True}
        if operation == "nack" and self.clock + delay > 1000000000:
            raise ValueError("retry delay exceeds the virtual clock range")
        message = self.messages[prior["message"]]
        if (
            prior["status"] != "leased"
            or message["status"] != "leased"
            or message["active_delivery"] != token
            or message["lease_until"] <= self.clock
        ):
            raise ValueError("delivery lease expired or no longer owns the message")
        if operation == "ack":
            message.update(
                status="acknowledged",
                active_delivery=None,
                lease_until=None,
                owner=None,
            )
            prior["status"] = "acknowledged"
        else:
            prior["status"] = "released"
            self.release(message, delay)
        receipt = {
            "id": message["id"],
            "status": message["status"],
            "attempt": prior["attempt"],
            "clock": self.clock,
        }
        prior.update(receipt=receipt, finish_binding=binding)
        return {**receipt, "reused": False}

    def release(self, message, delay):
        message.update(
            status=(
                "dead"
                if message["attempts"] >= self.configuration["max_deliveries"]
                else "queued"
            ),
            available_at=self.clock + delay,
            active_delivery=None,
            lease_until=None,
            owner=None,
        )

    def snapshot(self):
        messages = [
            copy.deepcopy(item)
            for item in sorted(self.messages.values(), key=lambda item: item["order"])
        ]
        return {
            "clock": self.clock,
            "message_count": len(messages),
            "deliveries": self.deliveries,
            "rejected_commands": self.rejections,
            "counts": {
                status: sum(item["status"] == status for item in messages)
                for status in ("queued", "leased", "acknowledged", "dead")
            },
            "messages": messages,
        }

