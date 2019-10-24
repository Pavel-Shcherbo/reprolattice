# HTTP/JSON capture

Capture sends requests to its configured upstream. It does not undo an upstream
operation. The default policy permits a loopback upstream and read methods only.
Remote origins, write methods and credential-bearing requests require separate
explicit options. HTTPS uses the standard verified connection behavior.

## Local walkthrough

Export the examples into a new writable directory:

```sh
python3 -m reprolattice.resources ./demo
```

Start the example dependency in one terminal:

```sh
python3 -m reprolattice serve demo/retry.json --port 9000
```

Start capture in another:

```sh
python3 -m reprolattice.capture http://127.0.0.1:9000 --output captured.json --port 9001
```

Point a test client at `http://127.0.0.1:9001`. The example inventory client reads
`REPROLATTICE_BASE_URL` from its environment. Stop capture with Ctrl-C after the
requests complete. The output includes completeness, failures, redaction and
concurrency metadata. A nonzero exit status is returned for an incomplete capture.

## Stored data

Request/response JSON is stored structurally, not as an identical byte stream.
Methods and paths are retained; known secret query values are replaced. Named
secret fields, authorization headers and cookies are removed from stored values
while an explicitly permitted live request still uses its original credentials.
Ordinary query encoding is preserved. Secret detection is not comprehensive;
review paths and application-specific data before sharing.

The capture enforces limits on payloads, stored bytes, interactions, parallel
requests, JSON structure and socket operations. Foreign browser origins are
rejected and upstream CORS grants are not relayed. These are local tool boundaries,
not authentication for a remotely exposed service.

Writes use a temporary file and atomic publication. An existing destination is
preserved unless overwrite is explicit. Incomplete output is retained as such and
cannot be verified as a complete scenario without deliberate review/correction.

## Replay and application checks

Recorded dependencies do not establish the correct application result. Add or
review `application.expected_json` before using the client harness. Protocol-only
verification checks the dependency fixture; client verification runs a trusted
local application and checks its output, exit code and interaction consumption.

Redaction may change values required for a faithful scenario. Recorded timing is
metadata and is not automatically replayed. Concurrent requests are flagged, but
their execution schedule is not reproduced. Duplicate header fields, binary or
streaming payloads and arbitrary application/database state need further adapters.
