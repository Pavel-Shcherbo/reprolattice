# Tasks

## Public repository status — 2026-11-04

Published with Pavel's explicit authorization at https://github.com/Pavel-Shcherbo/reprolattice.
The initial remote main matched qualified snapshot ff9e3a542093684fe235cb1a60776dd80a03226a.
The implemented local scope is qualified as recorded in docs/VERIFICATION.md.
This status supersedes earlier publication holds in the historical register below.
Earlier dates are a disclosed reconstruction; this publication record uses its actual date.
GitHub contribution-calendar rendering is checked separately and is not implied by a push.
No remaining local delivery blocker; future scope remains backlog.

---

## Current local qualification — 2026-11-04

Implemented scope: HTTP matching, real application output, SQLite postconditions, migration/reversal failures, queue redelivery/worker effects and saved portable histories. Full project suites passed on CPython
3.10–3.14: 269 tests per version. Clean wheel installation and CLI/API controls
passed on 3.10 and 3.14. [Current evidence](docs/VERIFICATION.md) supersedes old
size requirements and historical test totals below. Final package identities are maintained in the central review register;
no publication is authorized. Future provider/hosted/distributed
features in the original roadmap remain optional backlog.

---

Updated: 2026-11-04. Actual status only; historical roadmap rows remain proposed.

| Task | Status | Evidence | Remaining work |
|---|---|---|---|
| Core domain path | Implemented; 268 current tests passed | `reprolattice/`, `tests/` | Expand adversarial coverage as the model grows |
| Local CLI | Implemented; CLI end-to-end checks passed | `reprolattice/__main__.py`, `examples/` | Retained in the local verification evidence |
| Local workbench | Implemented; local HTTP and reviewed browser flows passed | `reprolattice/web.py`, `reprolattice/static/` | Retain checks as new screens and flows are added |
| Broad product scope | Planned | `docs/PRODUCT_SCOPE.md` | Most platform subsystems require implementation |
| Weekly reconstruction plan | Written | `docs/proposed-weekly-roadmap.csv` | Proposed commit counts are not actual commits |
| Publication | Waiting on Pavel | Current request: do not upload without Pavel | No push or hosted deployment |
| Production implementation ≥20,000 useful SLOC | Not achieved | 13795 project-specific SLOC measured; not achieved | Implement and verify the broad subsystem scope without padding |
| Explicit HTTP capture | Implemented; capture and CLI checks passed | `reprolattice/capture.py`, `tests/test_capture.py` | Request matchers and assertions implemented and verified; expand capture protocol coverage |
| Installable local package | Verified from a clean environment outside the source tree | `docs/installed-verification.json`, `_build.py`, `MANIFEST.in` | Cross-version/platform qualification remains open |
| Scenario suites and CI reports | Verified local increment; 89 total tests passed | `docs/SUITES.md`, suite/parameter/artifact/CLI/report tests and installed/browser evidence | Additional state providers, remote registry/CI qualification and broad scope remain open |
| SQLite application-state adapter | Verified local increment; 19 new tests, 108 total | `docs/SQLITE_STATE.md`, `docs/sqlite-state-verification.json` | Other providers, migration workflows, archive/browser management remain open |
| Immutable run registry and comparison gates | Verified local increment; 21 new checks, 129 total tests | `docs/RUNS.md`, `docs/run-registry-verification.json` | Archive/baseline UI, remote provenance/identity, paged full audits and retention remain open |

| Saved-run and baseline workbench | Verified local increment; 15 new checks, 167 current tests | `docs/ARCHIVE_WORKBENCH.md`, `docs/archive-browser-verification.json`, `docs/archive-workbench-verification.json` | Database-state review, additional providers, migrations, signed remote provenance, retention and full product/size scope remain open |

| Retained SQLite states and workbench | Verified local increment; 23 new checks, 167 current tests | `docs/STATE_WORKBENCH.md`, installed/browser/export/5,000-row workload evidence | Migration/provider workflows, retention/deletion, signed provenance and full scope/size remain open |

Next executable increments: managed provider protocols, scoped retention/deletion and broader source-database archive capture. Queue authoring/review is verified below. Queue workers, full queue command replay and independent SQLite effects are verified below.

Local reconstruction: five initial substantive stage commits created, plus verification, capture, matcher/assertion, suite/report, SQLite-state, run-registry and archive-workbench increments. No remote is configured; no upload was performed. The full dated roadmap remains proposed.

Current implementation verification: 268 tests passed, CLI checked, clean wheel installation and installed workbench HTTP checked. Broad scope and the 20,000-SLOC requirement remain open.

Verified increment: typed JSON-pointer application assertions, dynamic request matchers, shared CLI/workbench protocol verification and bounded process-output collection. 89 unit/integration tests passed; clean installed CLI and HTTP dynamic-scenario success/failure checks passed. Evidence: `docs/verification.json`, `docs/installed-verification.json`. The 20,000-SLOC and broad product requirements remain open.

Verified suite increment: typed parameter matrices, complete preflight, per-case workspace isolation, output-artifact assertions, bounded parallel execution, cancellation/fail-fast, case deadlines and JSON/JUnit/HTML report sets. 89 Reprolattice tests passed; clean installed suite and HTTP healthy/faulty checks passed. Browser JSON/JUnit downloads agree byte-for-byte; keyboard details, desktop/mobile and standalone HTML inspected. Evidence: `docs/verification.json`, `docs/installed-verification.json`, `docs/suite-browser-verification.json`, `docs/suite-download-verification.json`. Full product scope and the 20,000-SLOC requirement remain open.

Verified increment: structured SQLite fixtures, typed read-only postconditions, bounded logical snapshots and differences, and suite/JSON/JUnit/HTML integration. 19 new state tests and 108 total Reprolattice tests passed. Clean installed healthy suites passed; omitted-write suites failed despite correct HTTP results. Standalone snapshots/differences and report hashes passed. Evidence: `docs/SQLITE_STATE.md`, `docs/sqlite-state-verification.json`. Browser state inspection, other database providers, run collections and ≥20,000 useful SLOC remain open.

Verified increment: immutable local run archives, indexed case histories, generation-fenced passing baselines, source/parameter pairing, subject/fixture roles and explicit regression/coverage/context gates. 21 new checks and 129 total Reprolattice tests passed. Installed archive/retry/baseline/regression/fix/history/export/audit controls passed; current workbench suite HTTP remains healthy. Evidence: `docs/RUNS.md`, `docs/run-registry-verification.json`, `docs/run-registry-workbench-http.json`. SQLite-state inspection, signed provenance, retention/paged full audit and ≥20,000 useful SLOC remain open.

Verified increment: persistent saved-run review, newest-first indexed run history, coherent baseline snapshots, strict generation-bound comparisons, case history and saved JSON/JUnit exports. Fifteen new checks and 144 total Reprolattice tests passed. Clean installed API controls and real desktop/mobile browser saves, regressions/fixes, failed promotion, generation conflicts and deliberately delayed response checks passed. Downloaded reports/comparisons matched the archive and independent status/parameter pairing; JUnit counts and case identities matched JSON. Evidence: docs/ARCHIVE_WORKBENCH.md, docs/archive-workbench-verification.json, docs/archive-browser-verification.json. SQLite-state inspection, additional providers, migrations, signed remote provenance, retention/paged full audit and broad product/20,000 useful-SLOC scope remain open.

Verified retained SQLite increment: 23 new checks, 167 current Reprolattice tests; clean installed CLI/API, portable verification, independent typed row controls and real desktop/mobile browser downloads/races/recovery passed. A 5,000-row workload retained and compared correctly. Evidence: docs/STATE_WORKBENCH.md, docs/state-workbench-verification.json, docs/state-browser-verification.json, docs/state-benchmark.json. Current project-specific source: 8961 useful SLOC. Provider/migration workflows, retention/deletion, signed provenance and full product/20,000 useful-SLOC scope remain open. No publication.

Migration rehearsal implemented and verified below; broad product acceptance remains open.

Verified SQLite migration increment: 29 new checks; ordered isolated up/repeat/down cycles, exact restoration including hidden row identities and AUTOINCREMENT, atomic protected history, failure candidates and fresh offline SQL replay. Clean installed CLI controls and independent SQLite reads passed, including preserved source bytes and replay after removing the original source. A retained 5,000-row update/reversal workload passed. Evidence: docs/MIGRATIONS.md, docs/migration-verification.json and docs/migration-benchmark.json. Current project-specific source: 10099 SLOC. Migration browser, additional engines, remote provenance, production rollout, retention management and full product/20,000 useful-SLOC acceptance remain open. No publication.

| Isolated SQLite migration rehearsal | Verified local increment; 29 new checks and clean installed offline replay passed | `docs/MIGRATIONS.md`, `docs/migration-verification.json`, `docs/migration-benchmark.json` | Migration browser, other providers, remote provenance, production rollout and full scope/size remain open |

Earlier verification checkpoint: 196 Reprolattice tests and 572 portfolio tests passed; clean installed checks passed. Historical increment counts above are retained as evidence of their original scope. Full acceptance remains open.

Migration workbench implemented and verified below; full product/20,000 useful-SLOC acceptance remains open.

Verified migration-workbench increment: 17 new checks, 213 Reprolattice tests and 666 portfolio tests passed. Scoped retained rehearsals have input-bound idempotent receipts, lease/generation fencing, exact seed/plan checks and explicit adoption/interruption recovery. The browser exposes only three reviewed synthetic profiles, phase SQL/assertions, candidate/rolled-back tables, typed row changes and portable replay exports. Clean installed HTTP/CLI, independent downloaded SQLite/typed-state controls and real desktop/mobile browser checks passed, including persistence, delayed responses and lost-response retries. A retained 50-rehearsal workload produced 17 qualified results/33 reproducible failures with complete paged history. Evidence: docs/MIGRATION_WORKBENCH.md, docs/migration-workbench-verification.json, docs/migration-browser-verification.json and docs/migration-archive-benchmark.json. Current project-specific production source: 11278 SLOC. Additional providers, retention/deletion, signed remote provenance, general source-database archive capture and full product/20,000 useful-SLOC acceptance remain open. No publication.

| Retained migration workbench and portable archive | Verified local increment; 17 new checks, 268 current tests | `docs/MIGRATION_WORKBENCH.md`, installed/browser/download/recovery and 50-rehearsal evidence | Other providers, retention/deletion, remote provenance and full scope/size remain open |

Verified queue-adapter increment: 28 new checks, 241 Reprolattice tests and 763 portfolio tests passed. A bounded virtual-clock loopback queue provides ready-time delivery ordering, lease/owner tokens, delayed nack, exact publish/finish retries and dead-letter transitions. Known dropped commands and wire failures remain incomplete; slow headers have a total deadline. Existing suites support queue cases with independent SQLite/artifact checks, compact CI reports, separate create-only replay proofs and archive/baseline qualification. Real workers commit an effect then exit 17 before acknowledgement: both variants have identical passing queue histories, while independent SQLite checks retain stock 6 for the idempotent worker and detect stock 2 for the duplicate-effect variant. Clean installed standalone/suite/JUnit/archive controls passed, including failed-baseline rejection, passing-baseline promotion and broker replay after removing the worker. A 200-message/400-delivery/601-command workload matched a separate 200-effect/unit-sum-20100 oracle and replayed. Fixed macOS departed-process-group cleanup without suppressing errors for a live leader. Evidence: docs/QUEUES.md, docs/queue-verification.json and docs/queue-benchmark.json. Current project-specific production source: 12156 SLOC. Queue browser, hosted/provider wire adapters, retention/deletion, source-database archive capture, signed provenance and full product/20,000 useful-SLOC scope remain open. No external publication.

| Queue workers, redelivery and effect qualification | Verified local increment; 28 new checks and installed standalone/suite/archive controls | `docs/QUEUES.md`, `docs/queue-verification.json`, `docs/queue-benchmark.json` | Browser, provider protocols, retention and full scope/size remain open |

Verified queue-laboratory increment: 27 new checks, 268 Reprolattice tests and 836 portfolio tests passed. Scoped saved simulations retain atomic generation-fenced command batches and input-bound retry receipts; killed-process, quota and response failures leave no partial delivery. Complete histories can be forked, imports remain read-only and incomplete prefixes cannot become active simulations. Exact JSON text preserves large integers and export hashes. Reviewed real crash workers retain identical passing broker histories but independently observed SQLite stock 6/2 and distinct application outcomes. Clean installed CLI/API, create-only export, independent database reads and replay after database removal passed. Actual desktop/mobile controls passed network loss before/after commit, stale generation/acknowledgement, imports/forks, delayed selection, generation-aware history paging, row retry to dead letter and 32 unique records across sidebar pages. Downloaded simulation/worker exports replayed independently. A retained 40-session/1600-command/80-receipt workload matched the independent acknowledged-unit sum 8400. Evidence: docs/QUEUE_LAB.md, docs/queue-lab-verification.json, docs/queue-lab-benchmark.json and docs/queue-lab-browser-verification.json. Current project-specific production source: 13795 SLOC. Hosted/provider protocols, retention/deletion, source-database archive capture, signed provenance and full product/20000 useful-SLOC scope remain open. No publication.

| Saved queue laboratory and worker-effect review | Verified local increment; 27 checks, clean installed CLI/API, browser/download and 40-session workload | `docs/QUEUE_LAB.md`, `docs/queue-lab-verification.json`, `docs/queue-lab-browser-verification.json` | Hosted/provider protocols, retention and full size/scope remain open |


## Scope update — 2026-11-04

Pavel withdrew the mandatory 20,000-SLOC threshold: it was indicative. Earlier
size requirements in this log are superseded. Do not expand solely for line count.
Prioritize useful verified behavior and meaningful reconstructed history. Existing
verification evidence remains scoped to the versions it records; final acceptance
and full history reconstruction remain open. No publication is authorized.

History audit: actual local Git objects, ownership and nonempty stages were checked;
implementation/tests/examples match the last verified source version. The proposed
2019–2026 calendar remains a plan, not a completed activity record. The central
planning register retains the actual commit/calendar audit and outstanding work.

## Reconstructed history review — 2026-11-04

A separate disclosed local review history has been built from actual source
changes. Its final runtime matches the verified implementation; independently
restored copies passed the portfolio's 869 unit tests and three CLI controls.
Dates are illustrative labels; intermediate stages are not individually qualified
releases. Calendar/object/final-tree evidence and packaging status are maintained
in the central planning register (P-047). Original main history is retained.
Publication and final portfolio acceptance remain pending; no upload is authorized.

## Supported-Python final check — 2026-11-04

A real Python 3.10 run exposed unsupported authorizer disabling with None across
SQLite inspection/migration boundaries. A shared compatibility reset preserves
query-only and transaction controls; each user SQL execution reinstalls its policy.
The regression checks coherent inspection after success/rejection and denied
writes on the same read-only connection. Full version qualification is in progress.
No publication performed.
