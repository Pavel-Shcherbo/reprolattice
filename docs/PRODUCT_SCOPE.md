# Product scope

Proposed scope. Completion is tracked in TASKS.md; the weekly roadmap is not evidence of historical work.

## 2019: proposed development stages

### Q1: HTTP fixtures

Scope: ordered JSON request and response scenarios.

Acceptance: unknown requests receive a mismatch instead of upstream forwarding.

### Q2: Local capture

Scope: explicitly configured HTTP proxy recording.

Acceptance: capture does not persist excluded authorization or cookie fields.

### Q3: Request matching

Scope: method, path, query and structured body matchers.

Acceptance: ambiguous matches fail with an actionable explanation.

### Q4: Replay CLI

Scope: scenario lifecycle and machine-readable exit status.

Acceptance: an unconsumed or unexpected interaction fails verification.

## 2020: proposed development stages

### Q1: Sensitive field rules

Scope: nested JSON selectors and configurable redaction.

Acceptance: secret canaries are absent from every persisted artifact.

### Q2: Failure simulation

Scope: timeouts, response errors and reset connections.

Acceptance: the client observes the intended failure rather than a server crash.

### Q3: Stateful sequences

Scope: retry chains and scenario transition guards.

Acceptance: mismatched requests cannot advance the expected state.

### Q4: Fixture portability

Scope: schema versions, canonical ordering and relative paths.

Acceptance: a shared fixture runs without the author's filesystem layout.

## 2021: proposed development stages

### Q1: Application harness

Scope: test-process startup, readiness and cleanup.

Acceptance: failed startup leaves no unmanaged test processes.

### Q2: Database fixtures

Scope: explicit test-state loading and reset recipes.

Acceptance: scenario isolation prevents one test from changing another.

### Q3: Nondeterminism controls

Scope: declared clocks, generated IDs and normalization rules.

Acceptance: normalization cannot hide a changed business-critical field.

### Q4: Test export

Scope: standalone replay assertions and CI-compatible output.

Acceptance: the exported test fails on the original faulty application.

## 2022: proposed development stages

### Q1: Trace correlation

Scope: trace context, service spans and log links.

Acceptance: missing spans are shown as incomplete evidence.

### Q2: Scenario capture bundles

Scope: inputs, fixture references and application version.

Acceptance: a trace alone is never reported as a complete replay bundle.

### Q3: Behavior comparison

Scope: semantic JSON diffs and external call changes.

Acceptance: comparison preserves differences in error handling and side effects.

### Q4: Scenario browser

Scope: search, filters, replay state and failure details.

Acceptance: the interface distinguishes capture, replay and verification outcomes.

## 2023: proposed development stages

### Q1: Concurrency coverage

Scope: independent interactions and explicit ordering constraints.

Acceptance: unsupported scheduling races are reported instead of called deterministic.

### Q2: Queue adapters

Scope: message fixtures, acknowledgments and redelivery cases.

Acceptance: duplicate delivery does not silently create duplicate test effects.

### Q3: Protocol extensions

Scope: streaming response and gRPC adapter boundaries.

Acceptance: unsupported wire features fail before test execution.

### Q4: Contract checks

Scope: versioned API expectations and compatibility diffs.

Acceptance: a compatible schema change does not hide a semantic regression.

## 2024: proposed development stages

### Q1: Developer navigation

Scope: source links, scenario shortcuts and editor handoff.

Acceptance: paths remain useful across supported workspace layouts.

### Q2: Scenario authoring

Scope: fixture editing, validation and change previews.

Acceptance: invalid edits cannot replace the last valid scenario.

### Q3: Diagnostic reports

Scope: portable failure bundles with retained assertions.

Acceptance: a recipient can reproduce the case without account credentials.

### Q4: Performance investigation

Scope: repeat runs and timing-distribution comparison.

Acceptance: one observed duration is not presented as a reliable speedup.

## 2025: proposed development stages

### Q1: Team libraries

Scope: organization-scoped collections and review history.

Acceptance: workspace members cannot read another organization's captures.

### Q2: Retention policies

Scope: expiry, deletion verification and scoped access.

Acceptance: expired secrets and captures cannot remain in searchable derivatives.

### Q3: Network policies

Scope: loopback defaults and explicit dependency allowlists.

Acceptance: unexpected requests never reach real payment or messaging services.

### Q4: Large captures

Scope: bounded payloads, streaming storage and indexing.

Acceptance: large or malformed bodies cannot exhaust the capture service.

## 2026: proposed development stages

### Q1: SDK compatibility

Scope: versioned hooks and supported runtime matrix.

Acceptance: SDK upgrades preserve the declared fixture contract.

### Q2: Operational diagnostics

Scope: collector health and dropped-event counters.

Acceptance: partial capture is visible in the exported replay evidence.

### Q3: Scenario qualification

Scope: reviewed examples and failure-injection matrix.

Acceptance: each example proves both original failure and corrected behavior.

### Q4: Release packaging

Scope: local installation, upgrades and recovery instructions.

Acceptance: a clean machine completes the documented capture-to-test walkthrough.
