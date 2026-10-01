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

Implemented increment: 167 current tests passed; CLI and installed workbench entry points checked in a disposable clean environment. Current project-specific production source: 8961 SLOC, below 20,000. No publication.

Verified increment: typed JSON-pointer application assertions, dynamic request matchers, shared CLI/workbench protocol verification and bounded process-output collection. 89 unit/integration tests passed; clean installed CLI and HTTP dynamic-scenario success/failure checks passed. Evidence: `docs/verification.json`, `docs/installed-verification.json`. The 20,000-SLOC and broad product requirements remain open.

Verified suite increment: typed parameter matrices, complete preflight, per-case workspace isolation, output-artifact assertions, bounded parallel execution, cancellation/fail-fast, case deadlines and JSON/JUnit/HTML report sets. 89 Reprolattice tests passed; clean installed suite and HTTP healthy/faulty checks passed. Browser JSON/JUnit downloads agree byte-for-byte; keyboard details, desktop/mobile and standalone HTML inspected. Evidence: `docs/verification.json`, `docs/installed-verification.json`, `docs/suite-browser-verification.json`, `docs/suite-download-verification.json`. Full product scope and the 20,000-SLOC requirement remain open.

Verified increment: structured SQLite fixtures, typed read-only postconditions, bounded logical snapshots and differences, and suite/JSON/JUnit/HTML integration. 19 new state tests and 108 total Reprolattice tests passed. Clean installed healthy suites passed; omitted-write suites failed despite correct HTTP results. Standalone snapshots/differences and report hashes passed. Evidence: `docs/SQLITE_STATE.md`, `docs/sqlite-state-verification.json`. Browser state inspection, other database providers, run collections and ≥20,000 useful SLOC remain open.

Verified increment: immutable local run archives, indexed case histories, generation-fenced passing baselines, source/parameter pairing, subject/fixture roles and explicit regression/coverage/context gates. 21 new checks and 129 total Reprolattice tests passed. Installed archive/retry/baseline/regression/fix/history/export/audit controls passed; current workbench suite HTTP remains healthy. Evidence: `docs/RUNS.md`, `docs/run-registry-verification.json`, `docs/run-registry-workbench-http.json`. SQLite-state inspection, signed provenance, retention/paged full audit and ≥20,000 useful SLOC remain open.

Verified increment: persistent saved-run review, newest-first indexed run history, coherent baseline snapshots, strict generation-bound comparisons, case history and saved JSON/JUnit exports. Fifteen new checks and 144 total Reprolattice tests passed. Clean installed API controls and real desktop/mobile browser saves, regressions/fixes, failed promotion, generation conflicts and deliberately delayed response checks passed. Downloaded reports/comparisons matched the archive and independent status/parameter pairing; JUnit counts and case identities matched JSON. Evidence: docs/ARCHIVE_WORKBENCH.md, docs/archive-workbench-verification.json, docs/archive-browser-verification.json. SQLite-state inspection, additional providers, migrations, signed remote provenance, retention/paged full audit and broad product/20,000 useful-SLOC scope remain open.

Verified retained SQLite increment: 23 new checks, 167 current Reprolattice tests; clean installed CLI/API, portable verification, independent typed row controls and real desktop/mobile browser downloads/races/recovery passed. A 5,000-row workload retained and compared correctly. Evidence: docs/STATE_WORKBENCH.md, docs/state-workbench-verification.json, docs/state-browser-verification.json, docs/state-benchmark.json. Current project-specific source: 8961 useful SLOC. Provider/migration workflows, retention/deletion, signed provenance and full product/20,000 useful-SLOC scope remain open. No publication.

Migration rehearsal implemented and verified below; broad product acceptance remains open.

Verified SQLite migration increment: 29 new checks; ordered isolated up/repeat/down cycles, exact restoration including hidden row identities and AUTOINCREMENT, atomic protected history, failure candidates and fresh offline SQL replay. Clean installed CLI controls and independent SQLite reads passed, including preserved source bytes and replay after removing the original source. A retained 5,000-row update/reversal workload passed. Evidence: docs/MIGRATIONS.md, docs/migration-verification.json and docs/migration-benchmark.json. Current project-specific source: 10099 SLOC. Migration browser, additional engines, remote provenance, production rollout, retention management and full product/20,000 useful-SLOC acceptance remain open. No publication.

Current verification checkpoint: 196 Reprolattice tests and 572 portfolio tests passed; clean installed checks passed. Historical increment counts above are retained as evidence of their original scope. Full acceptance remains open.

Migration workbench implemented and verified below; full product/20,000 useful-SLOC acceptance remains open.

Verified migration-workbench increment: 17 new checks, 213 Reprolattice tests and 666 portfolio tests passed. Scoped retained rehearsals have input-bound idempotent receipts, lease/generation fencing, exact seed/plan checks and explicit adoption/interruption recovery. The browser exposes only three reviewed synthetic profiles, phase SQL/assertions, candidate/rolled-back tables, typed row changes and portable replay exports. Clean installed HTTP/CLI, independent downloaded SQLite/typed-state controls and real desktop/mobile browser checks passed, including persistence, delayed responses and lost-response retries. A retained 50-rehearsal workload produced 17 qualified results/33 reproducible failures with complete paged history. Evidence: docs/MIGRATION_WORKBENCH.md, docs/migration-workbench-verification.json, docs/migration-browser-verification.json and docs/migration-archive-benchmark.json. Current project-specific production source: 11278 SLOC. Additional providers, retention/deletion, signed remote provenance, general source-database archive capture and full product/20,000 useful-SLOC acceptance remain open. No publication.

Verified queue-adapter increment: 28 new checks, 241 Reprolattice tests and 763 portfolio tests passed. A bounded virtual-clock loopback queue provides ready-time delivery ordering, lease/owner tokens, delayed nack, exact publish/finish retries and dead-letter transitions. Known dropped commands and wire failures remain incomplete; slow headers have a total deadline. Existing suites support queue cases with independent SQLite/artifact checks, compact CI reports, separate create-only replay proofs and archive/baseline qualification. Real workers commit an effect then exit 17 before acknowledgement: both variants have identical passing queue histories, while independent SQLite checks retain stock 6 for the idempotent worker and detect stock 2 for the duplicate-effect variant. Clean installed standalone/suite/JUnit/archive controls passed, including failed-baseline rejection, passing-baseline promotion and broker replay after removing the worker. A 200-message/400-delivery/601-command workload matched a separate 200-effect/unit-sum-20100 oracle and replayed. Fixed macOS departed-process-group cleanup without suppressing errors for a live leader. Evidence: docs/QUEUES.md, docs/queue-verification.json and docs/queue-benchmark.json. Current project-specific production source: 12156 SLOC. Queue browser, hosted/provider wire adapters, retention/deletion, source-database archive capture, signed provenance and full product/20,000 useful-SLOC scope remain open. No external publication.

Verified queue-laboratory increment: 27 new checks, 268 Reprolattice tests and 836 portfolio tests passed. Scoped saved simulations retain atomic generation-fenced command batches and input-bound retry receipts; killed-process, quota and response failures leave no partial delivery. Complete histories can be forked, imports remain read-only and incomplete prefixes cannot become active simulations. Exact JSON text preserves large integers and export hashes. Reviewed real crash workers retain identical passing broker histories but independently observed SQLite stock 6/2 and distinct application outcomes. Clean installed CLI/API, create-only export, independent database reads and replay after database removal passed. Actual desktop/mobile controls passed network loss before/after commit, stale generation/acknowledgement, imports/forks, delayed selection, generation-aware history paging, row retry to dead letter and 32 unique records across sidebar pages. Downloaded simulation/worker exports replayed independently. A retained 40-session/1600-command/80-receipt workload matched the independent acknowledged-unit sum 8400. Evidence: docs/QUEUE_LAB.md, docs/queue-lab-verification.json, docs/queue-lab-benchmark.json and docs/queue-lab-browser-verification.json. Current project-specific production source: 13795 SLOC. Hosted/provider protocols, retention/deletion, source-database archive capture, signed provenance and full product/20000 useful-SLOC scope remain open. No publication.


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
