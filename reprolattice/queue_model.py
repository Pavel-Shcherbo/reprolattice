"""Explicit local queue fixture limits and final-state assertion contracts."""

import copy
import hashlib
import json
import re

from .assertions import compile_rules
from .harness import application_contract
from .jsonutil import validate_json

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")
MAX_EVIDENCE = 8 * 1024 * 1024


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def fingerprint(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def name(value, label):
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise ValueError(label + " requires a bounded ASCII identifier")
    return value


def integer(value, label, minimum=0, maximum=1000000000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer in {minimum}..{maximum}")
    return value


def fields(value, required, optional=()):
    if (
        not isinstance(value, dict)
        or set(value) - set(required) - set(optional)
        or not set(required) <= set(value)
    ):
        raise ValueError("queue document has missing or unsupported fields")


def configuration(value):
    fields(
        value,
        ("version", "name", "visibility_seconds", "max_deliveries", "messages"),
        ("max_messages", "max_commands", "max_body_bytes"),
    )
    validate_json(value, max_bytes=2 * 1024 * 1024)
    if type(value["version"]) is not int or value["version"] != 1:
        raise ValueError("queue fixture requires version 1")
    name(value["name"], "queue name")
    integer(value["visibility_seconds"], "visibility seconds", 1, 3600)
    integer(value["max_deliveries"], "max deliveries", 1, 20)
    result = copy.deepcopy(value)
    for key, default, maximum in (
        ("max_messages", 1000, 1000),
        ("max_commands", 5000, 5000),
        ("max_body_bytes", 65536, 65536),
    ):
        result[key] = integer(value.get(key, default), key, 1, maximum)
    messages = value["messages"]
    if not isinstance(messages, list) or len(messages) > result["max_messages"]:
        raise ValueError("seed messages exceed the declared queue capacity")
    ids = set()
    for item in messages:
        fields(item, ("id", "body"), ("delay_seconds",))
        identity = name(item["id"], "seed message ID")
        if identity in ids:
            raise ValueError("seed message IDs must be unique")
        ids.add(identity)
        integer(item.get("delay_seconds", 0), "seed delay", 0, 86400)
        validate_json(
            item["body"],
            max_bytes=result["max_body_bytes"],
            max_depth=30,
            max_nodes=10000,
        )
    return result


