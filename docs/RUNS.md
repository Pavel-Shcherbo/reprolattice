# Immutable run registry and regression gates

The registry retains canonical suite reports in a local SQLite database. It provides indexed run/case history, named passing baselines with generation checks, explainable comparisons and regenerated JSON/JUnit/HTML exports. It does not contact a hosted CI service, execute an imported report, or automatically accept a new baseline.

## Record an actual local run

```sh
python3 -m reprolattice.suites examples/inventory-suite.json --output .local/current-report --jobs 2
python3 -m reprolattice.runs --database .local/runs.sqlite init
python3 -m reprolattice.runs --database .local/runs.sqlite project-create inventory
python3 -m reprolattice.runs --database .local/runs.sqlite record inventory .local/current-report/report.json --revision "$(git rev-parse HEAD)" --request-key current-control
python3 -m reprolattice.runs --database .local/runs.sqlite list inventory
```

Use a new report directory/request key for a new run. Copy the archived `id` printed by `record` into subsequent commands; the quoted placeholder below must be replaced with that actual hash:

```sh
python3 -m reprolattice.runs --database .local/runs.sqlite baseline-move inventory main "<record-id>" --expected-generation 0 --reason "Initial reviewed passing suite"
python3 -m reprolattice.runs --database .local/runs.sqlite baseline inventory main
python3 -m reprolattice.runs --database .local/runs.sqlite get inventory "<record-id>"
python3 -m reprolattice.runs --database .local/runs.sqlite export inventory "<record-id>" --output .local/archived-report
```

`record` accepts a suite-report JSON file, not arbitrary JSON logs or a protocol-only report. Source/build `--revision` is a caller-supplied full lowercase 40/64-digit hash. The example uses this repository's current Git revision; other integrations must supply the revision/build identity appropriate to their subject. The registry does not authenticate that declaration against an external Git service.

A successful archive command exits 0 even when the stored suite failed. Report status remains explicit in its JSON and run listing. A comparison whose gate fails exits 1; a failed/incomplete audit exits 1; invalid input/storage or an existing output destination exits 2.

## Identity and immutability

The report is validated for finite bounded JSON, suite status/count consistency, timezone-aware start/finish order, unique case identities, valid hashes and check structures. A passed case must agree with its protocol/application, artifact and SQLite outcome records. Tag-filter exclusions must agree with selected-case counts.

Reports are stored as canonical JSON, so whitespace/key formatting in the original file does not create a different logical report. The archive ID identifies project, source/build revision, label, context, original run ID, suite, report hash and outcome summary. The real local archive timestamp is retained separately. There are no update/delete APIs for archived runs.

Request keys are scoped to a project and archive content/metadata. Identical retries return the original record with `reused: true`; conflicting requests fail. A run ID cannot be archived twice in one project with changed content or metadata. The same report can belong to another explicitly created project; projects are logical namespaces, not security tenants.

New suite reports capture the runner's Python version, operating-system name and machine architecture. These original values are the default comparison context when the report is imported. The importer's machine is not substituted. Old reports without context keep an empty context. `record --context FILE.json` explicitly supplies up to 32 bounded text metadata fields; this override remains caller-declared. The original report is still retained. Context and revision are not signed provenance.

Normal suite redaction remains in effect before archiving. Parameters retain an opaque hash computed before redaction so distinct secret-valued variants do not collapse into one case. Input/parameter hashes identify content; they are not encryption. The registry does not rewrite or infer arbitrary secrets in manually supplied reports. Local database files are owner-readable/writable when created.

## Fixture and subject file roles

Workspace file inputs accept optional `role: "fixture"` or `role: "subject"`. Omitted roles default to fixture:

```json
{"path":"inventory_client.py","sha256":"actual-file-sha256","role":"subject"}
```

A fixture is part of the test's conditions. A subject file is the application being tested. Both are pinned and copied into isolated workspaces exactly as before. Declaring a subject role does not weaken file hashes or permit arbitrary paths.

Modern case identity pairs source case ID with its parameter hash. Reordering a parameter matrix can change generated case IDs while preserving the same paired variants. The test-condition signature includes fixture contract, parameter identity/visible values, artifact assertions, timeout, fixture-role file pins and SQLite seed/check definitions. The subject signature includes command identity and subject-role file pins. A changed command or program can therefore be evaluated against the same test oracle.

Role choice is explicit; the tool does not guess from a `.py` extension. If a program is left as fixture-role input, its changed hash is treated conservatively as changed test conditions. Programs outside declared inputs are identified by command text, not by an automatically captured executable image; declare relevant source/binary files when that identity matters.

## Compare against a pinned baseline

After recording a candidate, replace the quoted placeholder with its archived ID:

```sh
python3 -m reprolattice.runs --database .local/runs.sqlite compare inventory main "<candidate-record-id>" --baseline --policy examples/run-gate-policy.json --output comparison.json
```

The named baseline is resolved to an immutable record ID and generation, retained as `baseline_resolution` in the result. A later baseline move cannot rewrite that result. Comparisons may also name two explicit record IDs. They must belong to the same project and suite name. Comparison JSON is published create-only and never overwrites an existing path.

Per-case classifications distinguish:

- `regressed`: comparable passed case becomes failed/error.
- `fixed`: comparable failed/error case passes.
- `stable_pass`, `stable_failure`, `changed_failure`: executed outcomes under unchanged test conditions.
- `changed_inputs`: the test-condition signature changed; a before/after status is retained without claiming a proven fix/regression under the same oracle.
- `lost_coverage`, `newly_executed`, `not_executed`: execution coverage changed or remains absent.
- `added_pass`, `added_failure`, `added_unexecuted`, `removed`: cases without a paired counterpart.

Independent flags/counts expose subject changes, input changes, lost execution coverage and affected identity fields. A case can have both changed inputs and lost coverage. Failure summaries remain bounded. Revision differences alone do not decide comparability; the recorded case identities and declared context do.

## Gate policy

The bundled `run-gate-policy.json` shows defaults. A partial policy object may override known fields only:

| Field | Default | Meaning |
|---|---|---|
| `require_full_suite` | true | Both reports must cover their full suite selection |
| `require_same_context` | true | Context must be known and equal |
| `allow_changed_inputs` | false | Otherwise changed test conditions block acceptance |
| `allow_removed` | false | Otherwise removed cases block acceptance |
| `allow_new_cases` | true | Added passing tests may be accepted; added failures still block |
| `allow_existing_failures` | false | Otherwise even unchanged existing failures block |
| `allow_legacy_metadata` | false | Otherwise missing modern case fingerprints block |
| `allow_tag_filtered` | false | Allows only explicitly tag-filtered exclusions, not cancellations/fail-fast |
| `max_slowdown_ratio` | null | Optional single-observation timing threshold |
| `minimum_duration_seconds` | 0.05 | Minimum positive baseline duration for timing checks |

Policy version is integer 1. Candidate failed/error cases always block unless they are comparable pre-existing failures and that exception is explicitly enabled. Cancelled or fail-fast/unstarted cases cannot be made passing by allowing tag-filter exclusions. Accepting a partial comparison requires both a scope policy and explicit excluded-case permission; the result still says `after_full_suite: false`.

Legacy reports may be archived and inspected. When modern fingerprints are unavailable, pairing falls back to generated case IDs and the result declares `legacy_case_id`. The default gate blocks that reduced evidence; an explicit policy can allow it. No missing hashes or execution environment are fabricated.

Timing uses two recorded durations, not repeated benchmark samples. It provides no statistical performance-confidence claim. It is evaluated only for comparable passed cases, with a finite ratio threshold from 1 to one million and positive minimum duration up to one hour. A zero baseline has no ratio. A ratio outside the finite numeric range is represented by null plus an overflow flag, while a configured applicable threshold still rejects that slowdown.

## Controlled baseline moves

Only a fully executed all-passing suite can become a named baseline. `baseline-move` requires a reason and exact current generation; creation expects generation 0. The update and append-only move event commit in one transaction. Concurrent/stale writers receive a generation conflict rather than replacing an unseen change. Even a passing candidate is not promoted automatically.

```sh
python3 -m reprolattice.runs --database .local/runs.sqlite baseline-history inventory main
python3 -m reprolattice.runs --database .local/runs.sqlite case-history inventory retry-quantity --status failed
python3 -m reprolattice.runs --database .local/runs.sqlite audit inventory
```

Baseline history is cursor-paged. Case history uses an individual case-row cursor, so a page boundary inside one run's matrix does not skip its other variants. History/list commands expose bounded indexed summaries; `get` validates archived payload identity, and `audit` also checks those indices against immutable reports.

## Export, audit and limits

Exports regenerate the standard JSON/JUnit/escaped HTML report set from validated archived JSON and create its completion manifest. Original HTML/XML input is not archived or executed; original source JSON formatting is not retained. Exports may therefore differ byte-for-byte from an earlier derived report set while preserving its report object. Existing directories and destination symlinks are refused.

Audits verify report/metadata hashes and validity, indexed case status/duration/signatures, baseline candidate eligibility, generation/event chains, current pointers and foreign keys. Audits are consistent read transactions and make no repair/deletion changes. An incomplete audit never returns `passed: true`.

Limits: 8 MiB/report, 100,000 JSON nodes, 256 cases/report; 10,000 archived runs and 1,000 named baselines per project. Context is at most 16 KiB with 32 text fields; labels 256 characters; baseline move reasons 512. Run/history pages accept 1–1,000 rows, with run metadata pages capped to 4 MiB. Audit is bounded to 1,000 runs, 64 MiB of report bytes, 50,000 cases and 10,000 baseline events per call. Stores exceeding a full-audit budget cannot receive a complete audit from this bounded command; paged complete verification and retention/compaction remain open. Reports and move history are retained without automatic cleanup.

The registry uses schema version 1, serialized SQLite writers and WAL. Missing registries require explicit initialization; unrelated/future schemas are rejected. Hashes detect inconsistency, not malicious replacement by an owner who can rewrite the entire database. Hosted identity/access control, signatures, remote registry synchronization, statistically qualified performance comparison and browser archive/baseline management remain open. Full product scope and 20,000 useful production SLOC remain open.
