"""A small retry client with an optional receipt for output-artifact checks."""

import argparse
import http.client
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--faulty", action="store_true")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    target = urlsplit(os.environ["REPROLATTICE_BASE_URL"])
    attempts = 1 if args.faulty else 3
    for _ in range(attempts):
        client = http.client.HTTPConnection(target.hostname, target.port, timeout=2)
        try:
            client.request("GET", "/inventory/part-42")
            response = client.getresponse()
            payload = json.loads(response.read())
            if response.status == 200:
                if args.receipt is not None:
                    args.receipt.write_text(json.dumps(payload) + "\n")
                print(json.dumps(payload))
                return 0
            if response.status not in {429, 502, 503, 504}:
                break
        finally:
            client.close()
    print(json.dumps({"error": "inventory request failed"}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
