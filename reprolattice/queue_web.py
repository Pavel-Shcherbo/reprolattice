"""Loopback queue laboratory; commands affect retained synthetic queues only."""

from .queue_lab import QueueLab
from .queue_model import canonical, fields
from .resources import examples_directory, state_directory
from .jsonutil import strict_json

PROJECT = "queue-workbench"


def evaluate_queue(params):
    action = params.get("action", "overview")
    root = state_directory("reprolattice") / "queue-workbench" / "queues.sqlite"
    if action == "example":
        fields(params, ("mode", "action"))
        fixture = strict_json((examples_directory() / "queue-orders.json").read_bytes())
        return {
            "configuration": fixture["queue"],
            "commands": [{"operation": "receive", "owner": "worker-a"}],
        }
    if action == "overview":
        fields(params, ("mode", "action"), ("before",))
        if not root.exists():
            from .queue_model import integer

            integer(params.get("before", 0), "list cursor", 0, 9223372036854775807)
            return {"items": [], "next_cursor": None}
        return QueueLab(root).list(PROJECT, before=params.get("before", 0))
    lab = QueueLab(root)
    if action == "view":
        fields(
            params,
            ("mode", "action", "record"),
            ("generation", "message_offset", "after", "case"),
        )
        return lab.view(
            PROJECT,
            params["record"],
            **{
                k: v
                for k, v in params.items()
                if k in ("generation", "message_offset", "after", "case")
            },
        )
    if action == "receipt":
        fields(params, ("mode", "action", "request_key"))
        result = lab.receipt(PROJECT, params["request_key"])
        return {**result, "response_json": canonical(result).decode()}
    if action == "export":
        fields(params, ("mode", "action", "record", "generation"))
        value = lab.export(PROJECT, params["record"], params["generation"])
        return {
            "content": canonical(value).decode() + "\n",
            "filename": "reprolattice-queue-"
            + value["session"]["id"]
            + "-g"
            + str(value["session"]["generation"])
            + ".json",
        }
    fields(params, ("mode", "action", "request_key", "payload"))
    payload = params["payload"]
    if isinstance(payload, dict):
        payload = dict(payload)
        for source, target in (
            ("configuration_json", "configuration"),
            ("commands_json", "commands"),
            ("evidence_json", "evidence"),
        ):
            if source in payload:
                if target in payload or not isinstance(payload[source], str):
                    raise ValueError("choose one JSON text or structured queue input")
                payload[target] = strict_json(payload.pop(source), max_nodes=4000000)
    result = lab.apply(PROJECT, params["request_key"], action, payload)
    return {**result, "response_json": canonical(result).decode()}
