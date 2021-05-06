# Tasks

Updated: 2026-11-04. Actual status only; historical roadmap rows remain proposed.

| Task | Status | Evidence | Remaining work |
|---|---|---|---|
| Core domain path | Implemented; 108 current tests passed | `reprolattice/`, `tests/` | Expand adversarial coverage as the model grows |
| Local CLI | Implemented; CLI end-to-end checks passed | `reprolattice/__main__.py`, `examples/` | Retained in the local verification evidence |
| Local workbench | Implemented; local HTTP and reviewed browser flows passed | `reprolattice/web.py`, `reprolattice/static/` | Retain checks as new screens and flows are added |
| Broad product scope | Planned | `docs/PRODUCT_SCOPE.md` | Most platform subsystems require implementation |
| Weekly reconstruction plan | Written | `docs/proposed-weekly-roadmap.csv` | Proposed commit counts are not actual commits |
| Publication | Waiting on Pavel | Current request: do not upload without Pavel | No push or hosted deployment |
| Production implementation ≥20,000 useful SLOC | Not achieved | 4697 project-specific SLOC measured; not achieved | Implement and verify the broad subsystem scope without padding |
| Explicit HTTP capture | Implemented; capture and CLI checks passed | `reprolattice/capture.py`, `tests/test_capture.py` | Request matchers and assertions implemented and verified; expand capture protocol coverage |
| Installable local package | Verified from a clean environment outside the source tree | `docs/installed-verification.json`, `_build.py`, `MANIFEST.in` | Cross-version/platform qualification remains open |
| Scenario suites and CI reports | Verified local increment; 89 total tests passed | `docs/SUITES.md`, suite/parameter/artifact/CLI/report tests and installed/browser evidence | Additional state providers, run collections, hosted CI qualification and broad scope remain open |

| SQLite application-state adapter | Verified local increment; 19 new tests, 108 total | `docs/SQLITE_STATE.md`, `docs/sqlite-state-verification.json` | Other providers, migration workflows, durable run collections and browser management remain open |

Next executable increment: retain immutable run collections and comparisons, then expose SQLite state checks and run history in the workbench. Additional database providers and migration workflows remain open.

Local reconstruction: five initial substantive stage commits created, plus verification, capture, matcher/assertion, suite/report and SQLite-state increments. No remote is configured; no upload was performed. The full dated roadmap remains proposed.

Current implementation verification: 108 tests passed, CLI checked, clean wheel installation and installed workbench HTTP checked. Broad scope and the 20,000-SLOC requirement remain open.

Verified increment: typed JSON-pointer application assertions, dynamic request matchers, shared CLI/workbench protocol verification and bounded process-output collection. 89 unit/integration tests passed; clean installed CLI and HTTP dynamic-scenario success/failure checks passed. Evidence: `docs/verification.json`, `docs/installed-verification.json`. The 20,000-SLOC and broad product requirements remain open.

Verified suite increment: typed parameter matrices, complete preflight, per-case workspace isolation, output-artifact assertions, bounded parallel execution, cancellation/fail-fast, case deadlines and JSON/JUnit/HTML report sets. 89 Reprolattice tests passed; clean installed suite and HTTP healthy/faulty checks passed. Browser JSON/JUnit downloads agree byte-for-byte; keyboard details, desktop/mobile and standalone HTML inspected. Evidence: `docs/verification.json`, `docs/installed-verification.json`, `docs/suite-browser-verification.json`, `docs/suite-download-verification.json`. Full product scope and the 20,000-SLOC requirement remain open.

Verified increment: structured SQLite fixtures, typed read-only postconditions, bounded logical snapshots and differences, and suite/JSON/JUnit/HTML integration. 19 new state tests and 108 total Reprolattice tests passed. Clean installed healthy suites passed; omitted-write suites failed despite correct HTTP results. Standalone snapshots/differences and report hashes passed. Evidence: `docs/SQLITE_STATE.md`, `docs/sqlite-state-verification.json`. Browser state inspection, other database providers, run collections and ≥20,000 useful SLOC remain open.
