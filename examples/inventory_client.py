"""Two small clients illustrating a missing and a working retry path."""

import http.client
import json
import os
import sys
from urllib.parse import urlsplit

target = urlsplit(os.environ["REPROLATTICE_BASE_URL"])
attempts = 1 if "--faulty" in sys.argv else 3
for attempt in range(attempts):
    client = http.client.HTTPConnection(target.hostname, target.port, timeout=2)
    try:
        client.request("GET", "/inventory/part-42")
        response = client.getresponse()
        payload = json.loads(response.read())
        if response.status == 200:
            print(json.dumps(payload))
            raise SystemExit(0)
        if response.status not in {429, 502, 503, 504}:
            break
    finally:
        client.close()
print(json.dumps({"error": "inventory request failed"}))
raise SystemExit(1)
