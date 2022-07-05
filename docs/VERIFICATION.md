# Initial-core verification

Verified locally on 2026-11-04. This is not full product acceptance.

- 129 domain, integration and negative-path tests passed.
- The documented CLI control scenario completed and its result was checked.
- Local HTTP success/failure scenarios and foreign-Origin rejection were checked.
- Desktop and mobile workbench screens were inspected; the review includes defect corrections.
- Broader product scope and the 20,000 useful production-SLOC requirement remain incomplete.

Run `python3 -m unittest discover -s tests -v` from this checkout. The examples and README describe supported behavior and limits. No remote publication or hosted deployment was performed.

Version 0.2 wheel installation was checked in an independent virtual environment from an unrelated working directory. Example export, CLI, static files and public workbench calculations passed. Installed code matched the source files, and runtime state remained outside the package. See installed-verification.json for the wheel identity.

The current increment adds typed JSON-pointer rules, dynamic request matching, shared protocol verification, bounded stdout/stderr, UTF-8 detection and POSIX descendant cleanup. New checks include real HTTP samples and subprocess failure cases. The installed dynamic example passes through CLI and the workbench API; an injected mismatch fails. Windows process-tree behavior is not qualified.

Suite verification covers typed matrix expansion, all-case preflight, file snapshots and pins, isolated concurrent cases, deterministic case ordering and event cursors, fail-fast, cancellation, CLI Ctrl-C reports, process/inspection deadlines, artifact hashes and assertions, tag-filter scope, secret canaries, XML/HTML escaping, report-count integrity and no-overwrite manifests. The bundled five-case suite passes; its faulty-client variant has three failures. Clean installed suite/HTTP checks and browser JSON/JUnit consistency passed. Desktop, 390-pixel mobile, keyboard case details and standalone HTML were inspected; full product acceptance remains open.

Verified increment: structured SQLite fixtures, typed read-only postconditions, bounded logical snapshots and differences, and suite/JSON/JUnit/HTML integration. 19 new state tests and 108 total Reprolattice tests passed. Clean installed healthy suites passed; omitted-write suites failed despite correct HTTP results. Standalone snapshots/differences and report hashes passed. Evidence: `docs/SQLITE_STATE.md`, `docs/sqlite-state-verification.json`. Browser state inspection, other database providers, run collections and ≥20,000 useful SLOC remain open.

State checks cover type distinctions, BLOB/null handling, relational seed preflight, read-only authorizer denial, recursive-query/row/byte/cancellation limits, logical insertion-order independence, schema/data differences, corrupted state, source pins and create-only exports. The installed suite checks demonstrate correct HTTP output with failed persistence. Prior browser evidence concerns the existing protocol/client/suite screens; SQLite state management has no browser UI yet.

Verified increment: immutable local run archives, indexed case histories, generation-fenced passing baselines, source/parameter pairing, subject/fixture roles and explicit regression/coverage/context gates. 21 new checks and 129 total Reprolattice tests passed. Installed archive/retry/baseline/regression/fix/history/export/audit controls passed; current workbench suite HTTP remains healthy. Evidence: `docs/RUNS.md`, `docs/run-registry-verification.json`, `docs/run-registry-workbench-http.json`. Browser archive/baseline management, signed provenance, retention/paged full audit and ≥20,000 useful SLOC remain open.

Registry controls include real healthy/faulty suite classification, stable matrix pairing after reordering/redaction, changed subject versus changed test conditions, partial/removed/cancelled coverage, legacy/unknown environment handling, finite extreme timing ratios, import immutability, concurrent baseline moves, cursor boundaries, archive/index/pointer corruption, safe export symlinks and operator exit codes. Installed controls archive two real local runs and verify three regressions, three fixes, stale-generation rejection, six case-history entries, ten indexed cases and regenerated export hashes. Registry management is CLI/library only; live workbench HTTP evidence covers the existing reviewed suite endpoint.
