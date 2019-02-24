import argparse
import http.client
import json
import threading
from pathlib import Path

from .replay import make_server, redact
from .harness import check_client


def main():
    parser = argparse.ArgumentParser(
        description="Serve, verify or redact a local HTTP scenario"
    )
    parser.add_argument("action", choices=["serve", "verify", "redact", "check-client"])
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        fixture = json.loads(args.fixture.read_text())
        if args.action == "redact":
            print(json.dumps(redact(fixture), indent=2))
            return
        if args.action == "check-client":
            report = check_client(fixture, args.command)
            print(json.dumps(report, indent=2))
            if not report["passed"]:
                raise SystemExit(1)
            return
        server, state = make_server(fixture, args.port if args.action == "serve" else 0)
    except (ValueError, OSError) as error:
        parser.exit(2, f"{error}\n")
    if args.action == "serve":
        print(
            f"Listening on http://127.0.0.1:{server.server_port}; no upstream forwarding",
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
            print(json.dumps(state))
        return
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    passed = True
    try:
        for item in fixture["interactions"]:
            connection = http.client.HTTPConnection(
                "127.0.0.1", server.server_port, timeout=3
            )
            request = item["request"]
            payload = json.dumps(request["json"]) if "json" in request else None
            connection.request(request["method"], request["path"], body=payload)
            response = connection.getresponse()
            content = response.read()
            passed = passed and response.status == item["response"].get("status", 200)
            if request["method"] != "HEAD" and response.status not in {204, 304}:
                passed = passed and json.loads(content) == item["response"].get("json")
            connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    passed = passed and state["consumed"] == state["total"] and state["unexpected"] == 0
    print(json.dumps({"passed": passed, **state}, indent=2))
    if not passed:
        raise SystemExit(1)


main()
