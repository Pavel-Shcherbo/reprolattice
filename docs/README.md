# Reprolattice guides

Reproduce a failure with an explicit fixture, inspect the real application effects and export evidence another developer can replay.

[Install and run](../README.md#run-the-workbench) · [Architecture](ARCHITECTURE.md) · [Verified scope](VERIFICATION.md)

## Choose a task

| Task | Guide | What to expect |
|---|---|---|
| Match and assert HTTP requests | [Assertions](ASSERTIONS.md) | Define request rules, typed bodies and application-result assertions. |
| Run a scenario matrix | [Suites](SUITES.md) | Preflight variants and retain JSON, HTML and JUnit reports. |
| Control retained executions | [Runs](RUNS.md) | Inspect durable run controls, interruption and retained outcomes. |
| Compare saved results | [Archive Workbench](ARCHIVE_WORKBENCH.md) | Select reviewed baselines and distinguish regressions from changed coverage. |
| Capture an HTTP dependency | [Capture](CAPTURE.md) | Use explicit target/write/credential options and review redaction boundaries. |
| Verify SQLite side effects | [Sqlite State](SQLITE_STATE.md) | Check database postconditions against real application execution. |
| Review state evidence in the browser | [State Workbench](STATE_WORKBENCH.md) | Inspect retained state observations and portable exports. |
| Test schema migration and reversal | [Migrations](MIGRATIONS.md) | Exercise explicit migration cases and failure paths. |
| Compare saved migration cases | [Migration Workbench](MIGRATION_WORKBENCH.md) | Review migration evidence and independently replay exports. |
| Model queue delivery and workers | [Queues](QUEUES.md) | Separate broker delivery histories from actual application effects. |
| Use the queue laboratory | [Queue Lab](QUEUE_LAB.md) | Fork saved simulations, inspect generation conflicts and replay real worker evidence. |

## Scope and evidence

The [verification record](VERIFICATION.md) describes the actual platform, Python-version and installed-package checks. Subsystem guides record their own increment-specific evidence; an old test total is not a current total.

[Product scope](PRODUCT_SCOPE.md) and the weekly roadmap include future ideas. They are not a checklist of completed features. Earlier Git dates are explicitly reconstructed; see the [history note](../README.md#history-note).

[Contributing](../CONTRIBUTING.md) explains local checks and how to report a reproducible problem.
