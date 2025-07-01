# Queue-backed application scenarios

The queue adapter runs a trusted local worker against a temporary loopback JSON
queue. It models visibility leases, explicit acknowledgements, delayed retries,
publication deduplication and dead-letter transitions. The same case can check
application artifacts and SQLite effects through the existing suite runner.

## Reproduce a real crash and duplicate side effect

Run from a source checkout, or export the installed examples with
`python3 -m reprolattice.resources demo` and replace `examples/` with `demo/`.
Use fresh report, proof and worker-workspace destinations.

```sh
python3 -m reprolattice.suites examples/queue-effects-suite.json --output .local/queue-reports --queue-evidence .local/queue-proofs --jobs 2
```

This regression-control suite intentionally returns exit 1: one case passes and
one fails. Both worker variants first launch a separate process, commit an inventory
change, write its unacknowledged delivery identity and terminate that process with
exit 17. The driver advances the fixture clock to expire its lease and receives
the same message again under a new delivery token. The old acknowledgement fails.

The idempotent worker records the message ID in the same SQLite transaction as
the effect; inventory moves from 10 to 6 once. The faulty variant applies the
effect again and leaves 2. Both variants return the same correct-looking JSON,
acknowledge the same messages and produce identical broker command histories.
The separate SQLite postcondition catches the faulty variant. Queue acknowledgements
alone do not prove exactly-once application effects.

The suite also verifies repeated acknowledgements, publication retry, two failed
poison-message deliveries and one dead-letter message. JSON, JUnit and standalone
HTML reports retain the case/check results. Complete broker histories are written
separately as `<case-id>.json` under the requested proof directory. Without
`--queue-evidence`, the compact suite report keeps their identities and check
outcomes, while the full history is not retained outside the temporary execution.

For a standalone protocol/application control:

```sh
mkdir -p .local/queue-worker
python3 -m reprolattice.queues run examples/queue-orders.json --cwd .local/queue-worker --output .local/queue.json --command python3 "$PWD/examples/queue_worker.py"
python3 -m reprolattice.queues verify .local/queue.json
```

The child command runs in `--cwd`; the absolute worker path keeps it independent
of that workspace. Suite commands copy the pinned worker into each isolated case
directory.

The standalone check evaluates application output and queue assertions. Add the
SQLite or artifact postconditions in a suite to qualify external effects. An
existing proof destination is never overwritten; creation uses private file
permissions and a complete temporary file followed by a create-only link.

## Queue fixture

`queue-orders.json` contains three contracts: `queue`, `application`, and a nonempty
`queue_assertions` list. `expected_rejections` is the exact number of model-level
rejections expected by the scenario, such as an expired delivery acknowledgement.
All other observed wire errors fail the run.

The queue configuration has `version: 1`, a name, `visibility_seconds` in 1–3600,
`max_deliveries` in 1–20 and seed `messages`. Each seed has a unique `id`, arbitrary
bounded JSON `body`, and optional `delay_seconds`. Optional limits can reduce
`max_messages`, `max_commands` and `max_body_bytes`. Terminal messages remain in
the retained history and count toward capacity.

Add `mode: "queue"` to a suite or case. Application commands, typed matrices,
source/subject file hashes, per-case isolation, cancellation, deadlines, artifact
assertions and SQLite postconditions use the normal suite contracts. Queue cases
also participate in the existing archive and passing-baseline checks. Other
application/protocol cases retain their previous behavior.

Queue proof bodies are exact fixture values, not a redacted production capture.
Queue cases therefore reject `secret_parameters` at preflight: they cannot promise
both byte-exact broker replay and the existing secret-export guarantee. Supply
synthetic queue fixture values. Ordinary process output uses the existing named-
field redaction. Proofs intentionally retain message bodies and ephemeral delivery
identities; the fixture's HTTP capability is never included.

## Worker interface

The harness supplies `REPROLATTICE_QUEUE_URL` and
`REPROLATTICE_QUEUE_CAPABILITY` to the worker. Send JSON to that URL with
`Content-Type: application/json` and `X-Queue-Fixture` set to the capability.
The fixture accepts its exact printed loopback host, no browser Origin and only
`POST /command`. Each accepted connection has a total two-second deadline.

| Operation | Additional fields | Result |
|---|---|---|
| `receive` | `owner` | One ready message with body, attempt, delivery token and lease end; or `message: null` |
| `ack` | `owner`, `delivery` | Acknowledge that exact unexpired attempt |
| `nack` | `owner`, `delivery`; optional `delay_seconds` | Release for a later retry, or dead-letter at the delivery limit |
| `publish` | `id`, `body`, `request_key`; optional `delay_seconds` | Create a message or recover the matching publication receipt |
| `advance` | `seconds` in 0–86400 | Advance virtual time and expire leases |
| `status` | None | Retained message state and counts |

The clock starts at zero and never advances by wall time. A lease is expired at
`clock >= lease_until`; a newly ready message is selected by readiness time then
insertion order. Expiry at the delivery limit moves the message to `dead` without
an extra delivery. An old token cannot acknowledge a newer attempt. An exact
repeated ack/nack returns its old receipt without changing current ownership;
changing its operation, owner or retry delay is rejected. Repeating a matching
publish key does not requeue an acknowledged or dead message. A changed body,
identity or delay under that key is rejected.

Commands from simultaneous workers are serialized at the fixture. This records
the actual observed order; it does not reproduce arbitrary thread scheduling or
model a particular hosted broker. Virtual time controls only this fixture's
visibility and availability. The worker and its descendants remain trusted local
programs, with the same process model as existing application suites.

## Replay and limits

Every retained command includes its computed response, virtual clock, sequence and
hash-chain parent. Verification constructs a fresh queue and reproduces the exact
responses and final state. Rehashed changes to state, attempts, responses or chain
links are rejected when they disagree with replay. Known unrecorded model attempts
and malformed/unsupported wire attempts make evidence incomplete; a command/byte
quota cannot leave an accepted, unjournaled mutation behind.

Offline verification reports `application_reexecuted: false` and
`source_authenticated: false`. It replays broker semantics, not the worker's code,
database effects, network packets or original host identity. An incomplete but
internally consistent prefix can verify for content and still returns incomplete
status/CLI exit 1. The live harness requires complete evidence for success.

Limits: 1,000 retained messages, 5,000 commands, 64 KiB per body, 128 KiB per HTTP
command and 8 MiB per proof. Conservative combined state/journal reservations can
reject an operation earlier; individually maximal inputs need not fit together.
JSON has structural limits. Slow/partial requests, capability failures, unsupported
methods, unexpected model rejections, process output overflow, timeout or cancellation
cannot produce a passing application check. The broker itself is temporary memory
state; this is not a durable or distributed queue service, RabbitMQ/SQS/Kafka wire
emulation, streaming protocol, or automatic production capture.

Verification: `queue-verification.json` records clean installed worker/suite/archive
controls and independent SQLite/JUnit checks. `queue-benchmark.json` records a
200-message/400-delivery workload and a separate idempotent effect oracle. Existing
HTTP, state, migration and workbench checks remain part of the full local test run.

A retained synthetic broker proof is included at `docs/queue-example-evidence.json`. Replay it with `python3 -m reprolattice.queues verify docs/queue-example-evidence.json`. This checks the broker history; it does not rerun the worker or its database effects.
