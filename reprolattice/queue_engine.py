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

