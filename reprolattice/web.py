import http.client
import json
import sys
import threading
from pathlib import Path

from .httpapp import serve
from .harness import check_client
from .replay import make_server

ROOT = Path(__file__).resolve().parents[1]


def example():
    return json.loads((ROOT / "examples/retry.json").read_text())


def evaluate(params):
    fixture = params.get("fixture", example())
    if not isinstance(fixture, dict):
        raise ValueError("fixture must be an object")
    if len(fixture.get("interactions", [])) > 100:
        raise ValueError(
            "The workbench supports at most 100 interactions per verification"
        )
    if params.get("mode") == "client":
        command = [sys.executable, str(ROOT / "examples/inventory_client.py")]
        if params.get("faulty_client"):
            command.append("--faulty")
        return check_client(fixture, command)
    server, state = make_server(fixture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    results = []
    try:
        for item in fixture["interactions"]:
            request = item["request"]
            path = request["path"]
            if params.get("inject_mismatch") and not results:
                path = "/unexpected-test-path"
            connection = http.client.HTTPConnection(
                "127.0.0.1", server.server_port, timeout=3
            )
            try:
                connection.request(
                    request["method"],
                    path,
                    json.dumps(request["json"]) if "json" in request else None,
                )
                response = connection.getresponse()
                raw = response.read()
                content = (
                    json.loads(raw) if raw and request["method"] != "HEAD" else None
                )
                expected = item["response"]
                passed = response.status == expected.get("status", 200) and (
                    request["method"] == "HEAD" or content == expected.get("json")
                )
                results.append(
                    {
                        "method": request["method"],
                        "path": path,
                        "expected": expected.get("status", 200),
                        "actual": response.status,
                        "body": content,
                        "passed": passed,
                    }
                )
            finally:
                connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    return {
        "results": results,
        **state,
        "passed": all(row["passed"] for row in results)
        and state["consumed"] == state["total"]
        and state["unexpected"] == 0,
    }


if __name__ == "__main__":
    serve(evaluate, example, 8413)
