# Request register

Source: Pavel, current project-planning chat, 2026-11-04.

| Request | Acceptance | Status |
|---|---|---|
| Build three substantial portfolio products | Independently usable implementations, meaningful verification and clear limits | In progress; Reprolattice has an initial working core |
| Distinctive names | Check indexed web and GitHub repository-name matches | `reprolattice` returned zero repository-name matches on 2026-11-04; not trademark clearance or a search-rank guarantee |
| Broad international scope | Concrete subsystem roadmap and independently extensible interfaces | Scope documented; scale and adoption not yet established |
| Detailed 2019–2026 allocation | Weekly deliverables, acceptance conditions and proposed commit dates | Written as an explicit reconstruction plan |
| Past-dated commits | Use reconstructed stage dates and preserve sole configured authorship | Initial local reconstructed stages created; author Pavel-Shcherbo (ID 44784481); no remote configured |
| Professional interface and documentation | Distinct product vocabulary, working controls, readable states and browser checks | Implemented; review in progress |
| Test independently; do not upload without Pavel | Local verification, no remote publication | Local checks in progress; upload withheld |

Requests from Julius or other team members: none in this project's current scope.

## Additional acceptance from Pavel

Each product must contain at least 20,000 useful production SLOC, excluding tests, documentation, fixtures, dependencies and generated outputs. Current implementations are far below this target. Broad implementation and independent verification remain in progress.

The contribution-date proposal allows 0–4 commits per day, rest days and breaks. It is a reconstruction plan, not completed historical work. The GitHub target is Pavel-Shcherbo; retain the existing author configuration. No upload without Pavel.

Implemented increment: 144 current tests passed; CLI and installed workbench entry points checked in a disposable clean environment. Current project-specific production source: 7195 SLOC, below 20,000. No publication.

Verified increment: typed JSON-pointer application assertions, dynamic request matchers, shared CLI/workbench protocol verification and bounded process-output collection. 89 unit/integration tests passed; clean installed CLI and HTTP dynamic-scenario success/failure checks passed. Evidence: `docs/verification.json`, `docs/installed-verification.json`. The 20,000-SLOC and broad product requirements remain open.

Verified suite increment: typed parameter matrices, complete preflight, per-case workspace isolation, output-artifact assertions, bounded parallel execution, cancellation/fail-fast, case deadlines and JSON/JUnit/HTML report sets. 89 Reprolattice tests passed; clean installed suite and HTTP healthy/faulty checks passed. Browser JSON/JUnit downloads agree byte-for-byte; keyboard details, desktop/mobile and standalone HTML inspected. Evidence: `docs/verification.json`, `docs/installed-verification.json`, `docs/suite-browser-verification.json`, `docs/suite-download-verification.json`. Full product scope and the 20,000-SLOC requirement remain open.

Verified increment: structured SQLite fixtures, typed read-only postconditions, bounded logical snapshots and differences, and suite/JSON/JUnit/HTML integration. 19 new state tests and 108 total Reprolattice tests passed. Clean installed healthy suites passed; omitted-write suites failed despite correct HTTP results. Standalone snapshots/differences and report hashes passed. Evidence: `docs/SQLITE_STATE.md`, `docs/sqlite-state-verification.json`. Browser state inspection, other database providers, run collections and ≥20,000 useful SLOC remain open.

Verified increment: immutable local run archives, indexed case histories, generation-fenced passing baselines, source/parameter pairing, subject/fixture roles and explicit regression/coverage/context gates. 21 new checks and 129 total Reprolattice tests passed. Installed archive/retry/baseline/regression/fix/history/export/audit controls passed; current workbench suite HTTP remains healthy. Evidence: `docs/RUNS.md`, `docs/run-registry-verification.json`, `docs/run-registry-workbench-http.json`. SQLite-state inspection, signed provenance, retention/paged full audit and ≥20,000 useful SLOC remain open.

Verified increment: persistent saved-run review, newest-first indexed run history, coherent baseline snapshots, strict generation-bound comparisons, case history and saved JSON/JUnit exports. Fifteen new checks and 144 total Reprolattice tests passed. Clean installed API controls and real desktop/mobile browser saves, regressions/fixes, failed promotion, generation conflicts and deliberately delayed response checks passed. Downloaded reports/comparisons matched the archive and independent status/parameter pairing; JUnit counts and case identities matched JSON. Evidence: docs/ARCHIVE_WORKBENCH.md, docs/archive-workbench-verification.json, docs/archive-browser-verification.json. SQLite-state inspection, additional providers, migrations, signed remote provenance, retention/paged full audit and broad product/20,000 useful-SLOC scope remain open.
