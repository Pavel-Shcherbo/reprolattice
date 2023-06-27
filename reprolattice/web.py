import json
import sys

from .httpapp import serve
from .harness import check_client
from .protocol import verify_protocol
from .resources import examples_directory
from .suite_web import evaluate_suite
from .archive_web import evaluate_archive
from .state_web import evaluate_state


def example():
    return json.loads((examples_directory() / "retry.json").read_text())


def evaluate(params):
    if params.get("mode") == "state":
        return evaluate_state(params)
    if params.get("mode") == "archive":
        return evaluate_archive(params)
    if params.get("mode") == "suite":
        return evaluate_suite(params)
    fixture = params.get("fixture", example())
    if not isinstance(fixture, dict):
        raise ValueError("fixture must be an object")
    if len(fixture.get("interactions", [])) > 100:
        raise ValueError(
            "The workbench supports at most 100 interactions per verification"
        )
    if params.get("mode") == "client":
        command = [sys.executable, str(examples_directory() / "inventory_client.py")]
        if params.get("faulty_client"):
            command.append("--faulty")
        return check_client(fixture, command)
    return verify_protocol(fixture, bool(params.get("inject_mismatch")))


if __name__ == "__main__":
    serve(evaluate, example, 8413)
