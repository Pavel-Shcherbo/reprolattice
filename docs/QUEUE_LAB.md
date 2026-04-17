# Saved queue laboratory

Open `/queues.html` from the local workbench. Create a queue from its editable
configuration, import an existing broker proof or saved laboratory export, or run
the reviewed crash-worker comparison. The sidebar lists retained scenarios newest
first and can load older pages.

The laboratory shares the exact `QueueEngine` semantics used by application
suites: explicit virtual time, ready-message ordering, visibility leases, fenced
ack/nack, publication retry keys and dead-letter transitions. It does not emulate
a hosted broker's network protocol. See [QUEUES.md](QUEUES.md).

## Author and execute

Create a queue with a label, configuration and synthetic messages. Each saved
simulation has a generation. Receive, Advance clock, Acknowledge and Retry message
act against the displayed generation. The command editor accepts a JSON array
of 1–50 operations, including `publish`, `receive`, `ack`, `nack`, `advance` and
`status`. The full operation schema is in the queue guide.

Every accepted laboratory batch commits its resulting history and response receipt
in one SQLite transaction. A model-level rejection is retained in that history
with status 400; other commands in the same batch still run. An infrastructure,
capacity or persistence failure rolls back the entire batch. Model quotas cannot
leave a partially saved delivery behind.

A new request key binds the exact action/inputs. An identical retry returns the
original response, even if the queue has since changed; reusing the key with
changed input fails. A tab saves its request before sending it. After a lost
response, Recover first looks up the receipt and only retries the original request
when none was committed. A changed generation is rejected rather than rebased.
The page can still acknowledge a saved write when its subsequent refresh fails.

Message payloads, command inputs and saved responses have exact JSON-text views.
The editor sends its original JSON text to the server: JavaScript must not round
large integers before submission. Downloads likewise save server-serialized text,
preserving numeric spellings such as `1.0` for canonical content hashes.

Views read one complete retained document. Message and command pagination carries
the displayed generation; a concurrent change refreshes the history instead of
mixing generations. Late responses cannot replace a newly selected scenario.

## Imports and forks

Broker evidence is verified before import. Saved laboratory envelopes also verify
their metadata/document identities before their contents are imported into a new
scoped record. The original project never chooses the destination project.
Imported histories are read-only. Incomplete prefixes remain explicitly incomplete
and cannot become active simulations.

Fork a complete simulation, import or selected worker case to continue its exact
configuration, state and command chain. The new simulation starts at generation 1
and records the parent's ID, generation and document hash. Its later commands do
not alter the parent. Lineage is a content reference, not authenticated provenance.

## Compare real worker effects

Run worker comparison executes only the pinned bundled synthetic workers. Both
variants write an inventory change in SQLite, crash a child process with exit 17
before acknowledgement and receive the message again. Their broker histories pass
and are byte-identical. The idempotent worker retains inventory 6; the faulty
worker retains 2. The independent database postcondition accepts the former and
rejects the latter.

The saved control keeps the suite report, both full broker proofs and typed
before/after SQLite snapshots. The browser shows application outcomes separately
from broker replay, with complete checks/snapshots available for inspection. The
faulty worker's failure remains visible; a successful control does not turn the
suite into an all-passing application run.

Replaying an exported control verifies both queue histories, snapshot identities,
report links, the known inventory/receipt observations and failure classification.
It does not rerun the worker process or authenticate the original machine. For
custom trusted application commands, use the existing queue suite CLI; browser
input cannot select an executable, arbitrary SQL or a filesystem path.

## Command line

Export examples, then create and advance a retained simulation:

```sh
python3 -m reprolattice.resources ./queue-demo
python3 -m reprolattice.queue_sessions --database .local/queue-lab.sqlite --project demo create queue-demo/queue-lab-configuration.json --label "Order retry" --request-key create-order
python3 -m reprolattice.queue_sessions --database .local/queue-lab.sqlite --project demo list
```

Use the returned session ID in place of `SESSION`:

```sh
python3 -m reprolattice.queue_sessions --database .local/queue-lab.sqlite --project demo commands SESSION queue-demo/queue-lab-commands.json --generation 1 --request-key retry-order
python3 -m reprolattice.queue_sessions --database .local/queue-lab.sqlite --project demo view SESSION --generation 2
python3 -m reprolattice.queue_sessions --database .local/queue-lab.sqlite --project demo receipt retry-order
python3 -m reprolattice.queue_sessions --database .local/queue-lab.sqlite --project demo export SESSION --generation 2 --output saved-queue.json
python3 -m reprolattice.queue_sessions verify saved-queue.json
```

The example receives attempt 1, expires its lease at clock 5 and receives attempt 2
under another owner. Copy the observed delivery token into an ack/nack operation,
or use the browser's message-row actions. `fork`, `import` and `workers` also accept
labels and request keys; `view` supports `--after`, `--message-offset` and `--case`.
Exports are create-only. Verification runs independently of the database.

Exit 0 means the requested laboratory action or complete content verification
succeeded. A saved rejected model command still has its own status 400 inside that
response. An incomplete imported export verifies its prefix and returns exit 1.
Invalid input, stale generation, quota rejection or storage failure returns exit 2.
The workers action returning 0 means the expected good/bad control was retained;
it does not mean both workers passed their application checks.

## Local state and bounds

Browser records live in `.local/reprolattice/queue-workbench/queues.sqlite` relative
to the server working directory. `REPROLATTICE_STATE_DIR` replaces the
`.local/reprolattice` root. The fixed browser project is `queue-workbench`; the CLI
allows explicitly named projects. Project scoping partitions local data, rather
than establishing OS-user authentication.

The loopback host requires its printed Host, matching Origin when supplied and
`X-Local-Request: 1`. HTTP inputs are strict finite JSON, at most 1 MiB; duplicate
keys are rejected. Larger evidence can be imported through the CLI. Queue-engine
bounds remain 1,000 messages, 5,000 commands, 64 KiB per body and 8 MiB per proof.
The laboratory accepts batches of at most 50 commands, at most 1,000 sessions,
10,000 operation receipts and 256 MiB of retained document/metadata/response content.
A saved combined worker document is bounded at 24 MiB.

Writes are serialized by SQLite, including the short reviewed worker control.
Process termination rolls back an uncommitted operation. Retrying that control may
rerun isolated temporary workers after an uncommitted crash; no live application
or remote effect is involved. This is a foreground local laboratory. Supervised
jobs, cancellation of a committed browser request, deletion/retention management,
secret payload redaction and hosted/provider protocols remain open. Payloads and
delivery identities are retained exactly; use synthetic input.

## Evidence

The new checks cover concurrent retries, competing generations, killed-process
rollback, quota/response failure, scoped reads/writes, fork isolation, incomplete
imports, exact JSON text, corrupted storage, full pagination, worker observations
and actual HTTP guards. Installed CLI/API checks include create-only export,
independent database reads and verification after removing the source database.
Actual desktop/mobile browser checks exercise lost replies before/after commit,
expired acknowledgement, imports, forks, paging across a change and delayed views.

- [Installed paths and independent observations](queue-lab-verification.json)
- [Retained-session workload](queue-lab-benchmark.json)
- [Browser/download checks](queue-lab-browser-verification.json)
- [Simulation export](queue-lab-example.json)
- [Real worker control export](queue-worker-control-example.json)

Full product and 20,000 useful-SLOC acceptance remain open.

Current local qualification: 27 new checks, 268 Reprolattice tests and 836 portfolio tests passed. Clean installation checks passed; size and full broad product acceptance remain open.
