# Tasks

Updated: 2026-11-04. Actual status only; historical roadmap rows remain proposed.

| Task | Status | Evidence | Remaining work |
|---|---|---|---|
| Core domain path | Implemented; 213 current tests passed | `reprolattice/`, `tests/` | Expand adversarial coverage as the model grows |
| Local CLI | Implemented; CLI end-to-end checks passed | `reprolattice/__main__.py`, `examples/` | Retained in the local verification evidence |
| Local workbench | Implemented; local HTTP and reviewed browser flows passed | `reprolattice/web.py`, `reprolattice/static/` | Retain checks as new screens and flows are added |
| Broad product scope | Planned | `docs/PRODUCT_SCOPE.md` | Most platform subsystems require implementation |
| Weekly reconstruction plan | Written | `docs/proposed-weekly-roadmap.csv` | Proposed commit counts are not actual commits |
| Publication | Waiting on Pavel | Current request: do not upload without Pavel | No push or hosted deployment |
| Production implementation ≥20,000 useful SLOC | Not achieved | 11278 project-specific SLOC measured; not achieved | Implement and verify the broad subsystem scope without padding |
| Explicit HTTP capture | Implemented; capture and CLI checks passed | `reprolattice/capture.py`, `tests/test_capture.py` | Request matchers and assertions implemented and verified; expand capture protocol coverage |
| Installable local package | Verified from a clean environment outside the source tree | `docs/installed-verification.json`, `_build.py`, `MANIFEST.in` | Cross-version/platform qualification remains open |
| Scenario suites and CI reports | Verified local increment; 89 total tests passed | `docs/SUITES.md`, suite/parameter/artifact/CLI/report tests and installed/browser evidence | Additional state providers, remote registry/CI qualification and broad scope remain open |
| SQLite application-state adapter | Verified local increment; 19 new tests, 108 total | `docs/SQLITE_STATE.md`, `docs/sqlite-state-verification.json` | Other providers, migration workflows, archive/browser management remain open |
| Immutable run registry and comparison gates | Verified local increment; 21 new checks, 129 total tests | `docs/RUNS.md`, `docs/run-registry-verification.json` | Archive/baseline UI, remote provenance/identity, paged full audits and retention remain open |

| Saved-run and baseline workbench | Verified local increment; 15 new checks, 167 current tests | `docs/ARCHIVE_WORKBENCH.md`, `docs/archive-browser-verification.json`, `docs/archive-workbench-verification.json` | Database-state review, additional providers, migrations, signed remote provenance, retention and full product/size scope remain open |

| Retained SQLite states and workbench | Verified local increment; 23 new checks, 167 current tests | `docs/STATE_WORKBENCH.md`, installed/browser/export/5,000-row workload evidence | Migration/provider workflows, retention/deletion, signed provenance and full scope/size remain open |

Next executable increment: provider extension boundaries and retention controls over isolated database evidence. Additional providers, migration workflows, signed provenance, paged full audit and retention remain open.

Local reconstruction: five initial substantive stage commits created, plus verification, capture, matcher/assertion, suite/report, SQLite-state, run-registry and archive-workbench increments. No remote is configured; no upload was performed. The full dated roadmap remains proposed.

Current implementation verification: 213 tests passed, CLI checked, clean wheel installation and installed workbench HTTP checked. Broad scope and the 20,000-SLOC requirement remain open.

Verified increment: typed JSON-pointer application assertions, dynamic request matchers, shared CLI/workbench protocol verification and bounded process-output collection. 89 unit/integration tests passed; clean installed CLI and HTTP dynamic-scenario success/failure checks passed. Evidence: `docs/verification.json`, `docs/installed-verification.json`. The 20,000-SLOC and broad product requirements remain open.

Verified suite increment: typed parameter matrices, complete preflight, per-case workspace isolation, output-artifact assertions, bounded parallel execution, cancellation/fail-fast, case deadlines and JSON/JUnit/HTML report sets. 89 Reprolattice tests passed; clean installed suite and HTTP healthy/faulty checks passed. Browser JSON/JUnit downloads agree byte-for-byte; keyboard details, desktop/mobile and standalone HTML inspected. Evidence: `docs/verification.json`, `docs/installed-verification.json`, `docs/suite-browser-verification.json`, `docs/suite-download-verification.json`. Full product scope and the 20,000-SLOC requirement remain open.

Verified increment: structured SQLite fixtures, typed read-only postconditions, bounded logical snapshots and differences, and suite/JSON/JUnit/HTML integration. 19 new state tests and 108 total Reprolattice tests passed. Clean installed healthy suites passed; omitted-write suites failed despite correct HTTP results. Standalone snapshots/differences and report hashes passed. Evidence: `docs/SQLITE_STATE.md`, `docs/sqlite-state-verification.json`. Browser state inspection, other database providers, run collections and ≥20,000 useful SLOC remain open.

Verified increment: immutable local run archives, indexed case histories, generation-fenced passing baselines, source/parameter pairing, subject/fixture roles and explicit regression/coverage/context gates. 21 new checks and 129 total Reprolattice tests passed. Installed archive/retry/baseline/regression/fix/history/export/audit controls passed; current workbench suite HTTP remains healthy. Evidence: `docs/RUNS.md`, `docs/run-registry-verification.json`, `docs/run-registry-workbench-http.json`. SQLite-state inspection, signed provenance, retention/paged full audit and ≥20,000 useful SLOC remain open.

Verified increment: persistent saved-run review, newest-first indexed run history, coherent baseline snapshots, strict generation-bound comparisons, case history and saved JSON/JUnit exports. Fifteen new checks and 144 total Reprolattice tests passed. Clean installed API controls and real desktop/mobile browser saves, regressions/fixes, failed promotion, generation conflicts and deliberately delayed response checks passed. Downloaded reports/comparisons matched the archive and independent status/parameter pairing; JUnit counts and case identities matched JSON. Evidence: docs/ARCHIVE_WORKBENCH.md, docs/archive-workbench-verification.json, docs/archive-browser-verification.json. SQLite-state inspection, additional providers, migrations, signed remote provenance, retention/paged full audit and broad product/20,000 useful-SLOC scope remain open.

Verified retained SQLite increment: 23 new checks, 167 current Reprolattice tests; clean installed CLI/API, portable verification, independent typed row controls and real desktop/mobile browser downloads/races/recovery passed. A 5,000-row workload retained and compared correctly. Evidence: docs/STATE_WORKBENCH.md, docs/state-workbench-verification.json, docs/state-browser-verification.json, docs/state-benchmark.json. Current project-specific source: 8961 useful SLOC. Provider/migration workflows, retention/deletion, signed provenance and full product/20,000 useful-SLOC scope remain open. No publication.

Migration rehearsal implemented and verified below; broad product acceptance remains open.

Verified SQLite migration increment: 29 new checks; ordered isolated up/repeat/down cycles, exact restoration including hidden row identities and AUTOINCREMENT, atomic protected history, failure candidates and fresh offline SQL replay. Clean installed CLI controls and independent SQLite reads passed, including preserved source bytes and replay after removing the original source. A retained 5,000-row update/reversal workload passed. Evidence: docs/MIGRATIONS.md, docs/migration-verification.json and docs/migration-benchmark.json. Current project-specific source: 10099 SLOC. Migration browser, additional engines, remote provenance, production rollout, retention management and full product/20,000 useful-SLOC acceptance remain open. No publication.

| Isolated SQLite migration rehearsal | Verified local increment; 29 new checks and clean installed offline replay passed | `docs/MIGRATIONS.md`, `docs/migration-verification.json`, `docs/migration-benchmark.json` | Migration browser, other providers, remote provenance, production rollout and full scope/size remain open |

Current verification checkpoint: 196 Reprolattice tests and 572 portfolio tests passed; clean installed checks passed. Historical increment counts above are retained as evidence of their original scope. Full acceptance remains open.

Migration workbench implemented and verified below; full product/20,000 useful-SLOC acceptance remains open.

Verified migration-workbench increment: 17 new checks, 213 Reprolattice tests and 666 portfolio tests passed. Scoped retained rehearsals have input-bound idempotent receipts, lease/generation fencing, exact seed/plan checks and explicit adoption/interruption recovery. The browser exposes only three reviewed synthetic profiles, phase SQL/assertions, candidate/rolled-back tables, typed row changes and portable replay exports. Clean installed HTTP/CLI, independent downloaded SQLite/typed-state controls and real desktop/mobile browser checks passed, including persistence, delayed responses and lost-response retries. A retained 50-rehearsal workload produced 17 qualified results/33 reproducible failures with complete paged history. Evidence: docs/MIGRATION_WORKBENCH.md, docs/migration-workbench-verification.json, docs/migration-browser-verification.json and docs/migration-archive-benchmark.json. Current project-specific production source: 11278 SLOC. Additional providers, retention/deletion, signed remote provenance, general source-database archive capture and full product/20,000 useful-SLOC acceptance remain open. No publication.

| Retained migration workbench and portable archive | Verified local increment; 17 new checks, 213 current tests | `docs/MIGRATION_WORKBENCH.md`, installed/browser/download/recovery and 50-rehearsal evidence | Other providers, retention/deletion, remote provenance and full scope/size remain open |
