# Architecture

## Current implementation

Fixture validation creates a private interaction list. A lock protects its sequence cursor. Each matching request consumes one expected interaction; a mismatch leaves the cursor unchanged and increments the unexpected counter. The server binds to loopback and has no upstream target. The workbench starts a temporary fixture server, sends control requests, closes it and reports the observed responses.

## Verification

Ordered failure/recovery responses, body mismatches, unknown paths, extra calls, recursive redaction, invalid headers and malformed fixtures; the faulty client fails and the corrected client passes the same scenario.

## Local HTTP boundary

The workbench binds to loopback, validates the Host header, rejects foreign
Origin values and requires a custom header for state-changing requests. Static
files are served from an explicit allowlist. Request bodies are limited to 1 MiB.
These measures support a local development tool; there is no production identity,
authorization or organization model yet.

## Matchers and assertions

`jsonutil` enforces finite bounded JSON at input boundaries, including unique object keys. `assertions` compiles non-executable pointer conditions, preserves boolean/number distinctions and reports redacted bounded diagnostics. `matching` combines method/path rules with optional header, query and JSON conditions. The replay server compiles matchers once and protects consumption with its sequence lock.

`protocol` is shared by CLI and workbench. Dynamic rules use an explicit concrete sample, validated before binding a temporary server. Protocol verification checks the fixture transport; the separate application harness checks actual client behavior.

## Process execution

`process` drains stdout and stderr concurrently into capped buffers, enforces a wall-clock deadline and reports invalid UTF-8 separately. POSIX process groups are terminated on timeout or output overflow, including descendants holding pipes after the leader exits. The harness combines output conditions, exit status, resource limits and interaction consumption. Windows descendant termination is not implemented or qualified; the harness is not an OS sandbox.

## Remaining boundaries

Saved-run, SQLite-state, migration and queue management views are implemented.
Additional database engines, signed remote provenance, streaming, concurrent
protocol replay scheduling and distributed execution remain outside the current
local tool. Bounded complete audits refuse an incomplete green result.

## Suite execution and CI reports

`parameters` expands bounded JSON matrices without evaluating expressions. `suite_config` compiles every case before execution, snapshots explicit workspace files and identifies the full resolved input set separately from the suite definition. `suite_runner` creates independent temporary workspaces and fixture servers, bounds concurrent submission and retains deterministic case ordering. Fail-fast, cancellation and case deadlines remain explicit outcomes.

`artifact_checks` validates declared JSON/text outputs without copying arbitrary files into reports. `reports` validates status/count consistency and exports JSON, escaped HTML and JUnit XML with a completion manifest and file hashes. `suites` is the local operator CLI; `suite_web` restricts HTTP-triggered execution to the reviewed bundled suite. See SUITES.md for scope, bounds and exit semantics.

## SQLite application state

`sqlite_seed` compiles structured constrained fixtures and publishes fresh databases without overwriting existing files. `sqlite_inspect` enforces read-only bounded query checks and creates canonical typed logical snapshots; query results are streamed under byte limits. `sqlite_state` integrates setup and coherent postcondition/snapshot reads into isolated suite cases. State checks contribute to case status and report failure summaries independently of HTTP output. `sqlite_cli` exposes create-only seed/snapshot operations and validated comparisons. See SQLITE_STATE.md for resource bounds and current logical-identity exclusions.

## Immutable run archive and comparisons

`run_contract` validates bounded execution evidence and separates test-condition identities from subject identities. The runner records original environment and parameter/assertion fingerprints; workspace files explicitly declare fixture/subject roles. `run_registry` transactionally archives canonical reports and indexed outcomes, with project scoping, idempotent imports and generation-checked baseline events. `run_compare` pairs cases by source/parameter identity and emits explicit status/input/coverage/context findings under a declared gate policy. `runs` supplies local operator commands and create-only comparison/export outputs. Imports never infer the execution environment from the importing host. See RUNS.md for trust boundaries and current bounds.


## Retained SQLite and migration review

`state_archive` retains bounded logical before/after evidence and typed table
changes for actual suite cases. `state_web` exposes scoped rows and portable
exports without accepting arbitrary filesystem paths over HTTP.

`migration_model` and `migration_sql` validate explicit ordered forward/reverse
plans. `migration_engine` applies them to an isolated SQLite seed or read-only
source copy, retaining failure candidates and restoration checks.
`migration_bundle` repeats the retained SQL/state proof offline.
`migration_archive` stores attempts and generations; `migration_web` runs reviewed
round-trip, statement-failure and broken-rollback controls. Neither the browser
nor rehearsal deploys SQL to the original user database. See
[state review](STATE_WORKBENCH.md), [migrations](MIGRATIONS.md) and
[migration workbench](MIGRATION_WORKBENCH.md).

## Queue delivery and actual worker effects

`queue_model` validates retained virtual-clock inputs. `queue_engine` controls
visibility, delivery tokens, expiry, deduplication and acknowledgement/redelivery.
`queue_http` exposes an isolated loopback worker protocol; `queue_harness` runs
trusted real workers under bounded process controls and reuses SQLite/artifact
postconditions. The crash control commits an effect before acknowledgement, then
checks whether redelivery duplicates that effect. Queue acknowledgement alone
never proves application idempotency.

`queue_lab` and `queue_sessions` retain saved scenarios, command histories,
generations, durable response receipts, read-only imports and explicit forks.
The browser preserves exact JSON text and exports server-produced evidence;
it does not round large integer inputs through a browser number conversion.
`queue_web` limits the application to its fixed local project and reviewed worker
controls. This is a reproducibility tool, not a hosted production broker. See
[queue scenarios](QUEUES.md) and [queue laboratory](QUEUE_LAB.md).
