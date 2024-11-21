# Retained migration review

Open the local workbench and choose **Migrations**. The screen rehearses a reviewed inventory schema change on a fresh isolated SQLite database, retains every completed result and lets you inspect failed candidates before transaction rollback.

The browser offers three synthetic controls:

- **Exact round trip** applies two migrations, checks duplicate requests, reverses them and verifies the exact original application state.
- **Fail after partial writes** creates/populates a table, then deliberately addresses a missing table. Candidate rows remain available as evidence; the working database is rolled back.
- **Incomplete reverse SQL** leaves applied data unchanged despite a reverse request. Exact restoration fails and the applied state remains inspectable.

These controls do not migrate an application database. Browser requests cannot submit SQL, commands or database paths. For your own reviewed SQL, use the migration CLI and its explicit seed/source options described in [MIGRATIONS.md](MIGRATIONS.md).

## Inspect a rehearsal

Select a retained run and a phase in **Execution steps**. The phase panel shows the executed direction, declared SQL/bound values, pre/postconditions, failure stage and snapshot identities. **Candidate** means the state captured before successful commit or failure rollback; it is not necessarily the final database state.

Choose a snapshot and table to inspect typed rows, or choose **Changes from before**. Changes compare the selected snapshot with that phase's original state. Hidden row identity is retained so a rowid change cannot pass as an exact reversal. A table removed by rollback can still exist in the candidate snapshot. Table data is paged at 25 entries; previous/next controls move through the retained page set. Assertions and schema are available separately from the row table.

**Replay retained SQL** runs the stored SQL against a fresh copy of the retained baseline. A failed qualification can have a successful evidence replay: that means its failure was reproduced, not that the migration passed. Completed records are bound to their original manifest and file hashes before inspection or export.

The interface protects selection state when responses arrive out of order. A table response for an earlier selection cannot replace the selected run. After a lost run response, retrying the same settings keeps the request key until its receipt is returned. Changing the control or label deliberately starts a new request.

## Persistence and recovery

State is stored under the separate local state directory's `migration-workbench/`. Its SQLite index scopes records by project and request key. Every rehearsal has its own bundle directory. A repeated request with different inputs is rejected; a repeated equal request returns the retained receipt without executing SQL again.

A pending run has an ownership token and a ten-minute lease. Completion verifies the bundle, reserved plan and exact seed baseline before committing the record. The lease is checked again at commit time. A stale owner cannot publish completion.

After an expired lease, **Reconcile interrupted run** verifies the existing evidence without rerunning the retained working database. Its verifier replays SQL on a disposable copy. If the complete bundle and reserved inputs verify, it adopts that bundle as completed. Otherwise it marks the record interrupted and keeps partial files. Generation checks reject stale reconciliation requests. To retry interrupted execution, explicitly run a fresh control with a new request key. No automatic cleanup, source write, retry of an unknown external effect or deletion occurs.

The local archive supports at most 1,000 records. Histories/bundles remain on disk; deletion, retention policy, remote access, other database providers and production rollout are separate unfinished platform work.

## Portable export

**Export replay bundle** downloads a JSON envelope containing the exact bundle files as base64, their manifest and the committed receipt. Verify a downloaded file without the workbench or original archive:

```sh
python3 -m reprolattice.migration_runs verify downloaded-migration.json
```

Verification materializes the bounded files into a temporary directory, validates the receipt/manifest binding and independently replays the migration SQL. File names are restricted to the bundle's exact fixed files and content-addressed snapshot paths. It rejects unsafe paths, bad encodings, changed manifests and inconsistent data.

Portable envelopes support at most 8 MiB of raw files and 12 MiB of JSON. Larger local bundles remain available through the underlying CLI directory workflow. The envelope includes raw database data; review it before sharing. Content hashes and local replay do not authenticate external authorship or establish production execution history.

## CLI archive workflow

```sh
python3 -m reprolattice.migration_runs --archive .local/rehearsals --project inventory \
  run examples/inventory-migrations.json --seed examples/inventory-seed.json \
  --request-key reviewed-round-trip --label "Inventory schema review"
python3 -m reprolattice.migration_runs --archive .local/rehearsals --project inventory list
python3 -m reprolattice.migration_runs --archive .local/rehearsals --project inventory inspect RECORD
python3 -m reprolattice.migration_runs --archive .local/rehearsals --project inventory \
  export RECORD --output migration-evidence.json
```

`recover RECORD --generation N` performs the same fenced adoption/interrupt decision as the browser. Exports are create-only. CLI status 0 means a qualified completed result or successful listing/export; 1 means a completed failed qualification or a pending/interrupted result; 2 means invalid inputs/evidence or I/O failure. A valid failed envelope therefore verifies its contents while still returning 1 for qualification.

## Retained verification

Seventeen new archive/API/CLI tests cover identical retries and restarts, project scope, failed candidates, incomplete reversal, export without an archive, envelope paths/encodings, file and manifest corruption, concurrent requests, preparation interruption, adoption without rerun, stale tokens/generations, commit-time expiry, seed binding, pagination and browser input boundaries.

Clean installed HTTP and CLI evidence is in `migration-workbench-verification.json`. Real browser checks cover three profiles, typed candidate rows, replay, downloaded evidence, persistent reload, delayed responses, lost-response receipt recovery and desktop/mobile layout. Their evidence is `migration-browser-verification.json`; reviewed screenshots are `migration-desktop.png` and `migration-mobile.png`.

`migration-archive-benchmark.json` retains a 50-rehearsal workload with 17 qualified results, 33 reproducible failures and complete three-page listing. All completed bundles were hash-checked. This local measurement does not qualify a hosted service or establish a production SLA. Full product and size acceptance remain open.
