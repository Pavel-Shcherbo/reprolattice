import argparse
import json
from pathlib import Path

from .replay import make_server, redact
from .harness import check_client
from .protocol import verify_protocol
from .jsonutil import strict_json


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
        fixture = strict_json(args.fixture.read_bytes(), max_bytes=16 * 1024 * 1024)
        if args.action == "redact":
            print(json.dumps(redact(fixture), indent=2))
            return
        if args.action == "check-client":
            report = check_client(fixture, args.command)
            print(json.dumps(report, indent=2))
            if not report["passed"]:
                raise SystemExit(1)
            return
        if args.action == "verify":
            report = verify_protocol(fixture)
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


main()
