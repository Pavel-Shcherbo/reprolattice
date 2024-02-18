# Rehearse SQLite migrations

Run explicit forward and reverse SQL against a private database copy. The source is opened read-only and copied through SQLite backup; committed WAL contents are included. This command never applies a migration to the source database.

```sh
python3 -m reprolattice.migrations run examples/inventory-migrations.json \
  --seed examples/inventory-seed.json --output .local/migration-control
python3 -m reprolattice.migrations verify .local/migration-control
```

Create `.local` first if needed. Output must be a new directory. For an existing database, replace `--seed` with `--source /path/to/source.sqlite`. After installation, export examples with `python3 -m reprolattice.resources demo` and use `demo/` paths.

## Plan contract

Version 1 requires `name`, `baseline_checks` and 1–16 ordered `migrations`. Each migration has a unique `id`, `before_checks`, `up`, `after_checks`, `down` and `rollback_checks`. Each check group contains 1–32 read-only query definitions using the existing typed SQLite query contract. Each direction contains 1–64 objects with `id`, a single `sql` statement and `parameters`. Values are bound, never interpolated into SQL. Null, text, integer, real and explicit `{"$blob":"00ff"}` values retain their types.

The inventory example creates a totals table, copies the aggregate, increments stock, checks both versions, then reverses both changes. Plan compilation validates the whole declaration before creating an output directory. Invalid source databases or failures while preparing copies can leave an incomplete output directory; without a final manifest it is not verified evidence.

## Transaction and reversal rules

For each forward step, the runner opens its own transaction, checks the expected prefix, runs preconditions, executes each single statement, runs postconditions and captures the candidate application state. Protected stack and hash-chained history changes commit in that same transaction. Repeating an applied forward step is observational: it does not rerun SQL or append history. The runner then reverses steps in order and repeats each reverse request as an already-absent check.

Reverse SQL must restore the original schema SQL, typed rows, hidden row identities and included internal sequence/statistics tables exactly. Physical page layout is not compared. A logically equivalent reformatted schema can fail this strict contract. An AUTOINCREMENT insert followed only by deleting that row is insufficient: the sequence changed. Foreign-key validity and quick integrity checks gate acceptance.

A failed statement, precondition, postcondition or reversal triggers rollback. The report retains the failure stage, failing statement ID, before/candidate/after snapshot identities, and whether rollback was independently confirmed. The candidate may be unavailable when it exceeds diagnostic or retention limits; `diagnostic_error` explains this. Deferred foreign-key failures can be retained for diagnosis, with up to 21 violation records. Such a candidate is never qualified as valid. Cancellation has a distinct status and cannot claim a full offline replay.

## Evidence and verification

A completed rehearsal directory contains `plan.json`, `report.json`, `baseline.sqlite`, `working.sqlite`, content-addressed `snapshots/` and `manifest.json`. The working copy includes protected rehearsal history; application snapshots exclude those two metadata tables. Exporting the directory also exports raw application data. Use reviewed synthetic or appropriately sanitized inputs. The named sensitive-field refusal uses the existing exact normalized secret-name list; it is not comprehensive data discovery or redaction.

Verification checks the exact file inventory, byte hashes, snapshot identities, working database and history, then executes the retained SQL on a fresh copy of the retained baseline. Logical outcomes must agree, including failed outcomes. Invocation ID, runtime version observations and wall-clock duration are excluded from semantic equality. A valid failure bundle can therefore have `passed: true` for evidence verification and `qualification_passed: false` for the migration itself. The CLI returns 0 only for a qualified migration, 1 for retained failed/cancelled qualification and 2 for invalid inputs or evidence.

Hash checks and local replay do not authenticate the source or author. This is local rehearsal evidence, not a production migration service, signature or deployment approval. Original source files are unnecessary for offline replay once the complete bundle is retained.

## Bounds and supported SQL

Each database is at most 16 MiB. Plans are at most 4 MiB with 1 MiB combined SQL and 64 KiB per statement. A step has a five-second/two-million-instruction budget; diagnostics use separate bounded cleanup budgets. Returned statement results are capped at 1,000 rows/1 MiB. Snapshots inherit typed SQLite row/cell/schema bounds; hidden row identity uses one column of that budget. The runner reserves two tables for its metadata, permits at most 64 distinct retained states/32 MiB, and caps bundle inventory at 80 MiB.

Ordinary main-database tables, indexes, views, triggers, DML and supported ALTER operations are allowed under a deny-by-default SQLite authorizer. Runner transaction control, protected metadata access, attached databases, temporary objects, virtual tables, PRAGMA statements, extension loading and unlisted functions are refused. Trigger side effects pass through the same authorization. Tables that shadow all three hidden-row aliases cannot be qualified. WITHOUT ROWID tables are supported without synthetic row identity.

Run reviewed local SQL. The authorizer and budgets are not an operating-system sandbox. SQL behavior can depend on SQLite version and functions; nondeterministic or environment-dependent SQL may fail fresh replay. Current evidence covers Python 3.14.6/SQLite 3.53.4 on macOS arm64. Other runtime/platform combinations, other database engines, a migration browser interface, remote provenance and production rollout remain open.

## Retained checks

`tests/test_migrations.py` covers successful/repeated cycles, partial DDL/DML failures, postcondition failures, inexact reversal, ordering/checksum guards, SQL policy, bound values, work/result limits, cancellation, hidden identities, AUTOINCREMENT, WAL copying, ALTER/WITHOUT ROWID, deferred foreign keys, triggers, create-only outputs and tamper/replay controls. Installed CLI evidence is in `migration-verification.json`; the retained 5,000-row update/reversal workload is described in `migration-benchmark.json`. These checks establish this local increment, not full product acceptance.
