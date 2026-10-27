# SQLite application-state checks

A correct HTTP response does not prove that an application persisted its result. SQLite state definitions add an isolated initial database and explicit postconditions to each suite case. Existing command, fixture, timeout, cancellation, parameter matrix and report semantics continue to apply.

## Run the inventory control

```sh
python3 -m reprolattice.suites examples/inventory-state-suite.json --output .local/state-report --jobs 2
```

Use a new report directory each time. From an installed wheel, export examples with `python3 -m reprolattice.resources demo` and use `demo/inventory-state-suite.json` instead.

Each of three matrix variants receives its own inventory database with quantity 99. The application retries a synthetic dependency, updates inventory to 0, 7 or 12, and inserts exactly one receipt in the same transaction. Two SQL queries verify both the inventory and receipt. No external database or service is contacted.

The example application supports `--omit-write` to demonstrate a defect: the correct JSON is printed, all HTTP interactions are consumed, but neither table is updated. Adding this argument to a local copy of the suite's `command` causes all three state checks to fail while the HTTP/application-output checks pass. The faulty suite exits 1 and its JSON/JUnit/HTML reports identify the failing SQLite state. This is an intentional defect control, not an expected successful suite.

## Suite definition

Add a `sqlite` list to a case. Parameter expansion happens before compilation, including typed expected rows. At most four databases are supported per case:

```json
{
  "path": "inventory.sqlite",
  "seed": "inventory-seed.json",
  "seed_sha256": "exact lowercase SHA-256 of that file",
  "checks": [
    {
      "id": "stock",
      "sql": "SELECT part, available FROM inventory ORDER BY part",
      "expected": [{"part": "part-42", "available": 7}],
      "order": "ordered"
    }
  ]
}
```

The hash above is explanatory; use an actual digest or omit the optional field. `seed` can also be an inline seed object; a `seed_sha256` is valid only with a file source. All variants and source pins are compiled before a case starts. Resolved seed/query identities are included in the suite snapshot hash and case metadata.

Database paths must remain within the fresh case directory. They cannot duplicate or overlap workspace input files, other database paths or reserved SQLite sidecar paths. State is created before the application runs, inspected after its process finishes, and removed with the case workspace after the suite. Trusted application programs run with ordinary user privileges; this is isolation of test inputs, not an operating-system sandbox.

## Structured seed contract

A seed object contains exactly `version: 1` and a `tables` array. A table requires `name`, `columns`, `rows`; optional fields are `primary_key`, `unique`, `foreign_keys`. Identifiers contain ASCII letters, digits or underscores, start with a letter or underscore, and contain at most 64 characters. Table and column names are checked for case-insensitive duplicates. Reserved `sqlite_` table names are rejected.

A column has exactly `name`, `type`, `nullable`. Types are INTEGER, REAL, TEXT or BLOB. Tables use SQLite STRICT storage and require a SQLite runtime that supports it. INTEGER inputs are signed 64-bit integers; REAL inputs are finite JSON floating-point values; text is at most 64 KiB. Booleans do not stand in for integers. A BLOB is `{"$blob":"00ff"}` with lowercase even-length hexadecimal, at most 64 KiB decoded. Null is permitted only in explicitly nullable columns. Every seed row supplies every declared column exactly once; there are no implicit defaults or SQL expressions.

A primary key is a list of non-nullable columns. `unique` is a list of column lists; nullable unique values follow SQLite's multiple-null behavior. A foreign key has `columns`, `table`, `references`, `on_delete`; the referenced columns must be a declared primary/unique key with matching storage types. Supported delete actions are RESTRICT, CASCADE and SET NULL, the last requiring nullable child columns. References are deferred until commit, so parent/child table input order is not significant. Duplicate keys and unresolved non-null references are rejected during preflight.

Seed limits: 32 tables, 64 columns per table, 16 unique constraints and 16 foreign keys per table, 10,000 rows per table, 20,000 total rows, 100,000 cells and 4 MiB of JSON. A database is created through a private temporary file and published create-only with a hard link. Existing files or symlinks are never overwritten. The generated database is limited to 16 MiB. Publication does not claim cross-directory power-loss durability.

## Typed read-only query assertions

Each state requires 1–32 queries. A query has `id`, `sql`, `expected`, optional positional `parameters` and `order`. SQL text is at most 64 KiB; at most 1,000 positional parameters are accepted. Parameters use the same bounded SQLite scalar/BLOB encoding as seed cells. Values are bound, never interpolated as SQL.

Expected results are row objects keyed by distinct SQL result aliases. Empty expected results require no rows. At most 64 columns, 1,000 rows and 1 MiB of actual result JSON are retained per query. Duplicate aliases are an error. Storage types remain explicit: INTEGER 1 differs from REAL 1.0 and TEXT "1". Null and binary values are distinct. Ordered checks compare row sequence; unordered checks compare multisets and preserve duplicate multiplicity. Specify an ORDER BY whenever sequence matters.

Connections open in read-only URI mode and enable query-only behavior. An authorizer permits SELECT/READ, bounded recursive reads and an explicit set of ordinary aggregate/text/numeric/JSON/window functions. Write statements, ATTACH/DETACH, transactions, PRAGMAs, extension loading and unlisted functions are denied. A function unavailable in the current SQLite runtime produces a failed query. Multiple SQL statements are not accepted. This restricts postcondition queries; the application under test itself is still a trusted executable.

Inspection uses a two-second deadline and a two-million virtual-machine-instruction budget. A direct library call can select a timeout up to ten seconds. Progress callbacks enforce cancellation during SQLite execution; external lock waits are bounded. Case deadlines are also checked around setup and inspection. Seed construction is bounded and cancellation is checked between setup stages. A timeout, cancellation, incomplete query or missing database cannot become a passing state.

## Logical snapshots and differences

A logical snapshot includes user schema objects, column metadata and typed rows of ordinary tables. Internal `sqlite_` objects and implicit rowids are excluded. Applications depending on automatic sequence counters or implicit rowids should declare explicit queries for those values; they are not part of logical row identity. Table rows are sorted canonically with duplicate multiplicity preserved; physical page placement and insertion order do not affect identity. Declared schema text is retained literally, so semantically similar but differently written DDL can have different schema identities. This is not a general SQL-schema equivalence engine.

Before acceptance, snapshot inspection performs quick integrity and foreign-key checks. Virtual tables, unavailable schema text, excessive data and invalid storage values fail explicitly. SQLite result lengths and expression/column/parameter limits are configured. The main file is limited to 16 MiB, WAL/journal sidecars to 16 MiB each and SHM to 1 MiB; symlink inputs and sidecars are refused.

Snapshot limits are 256 schema objects, 64 tables, 64 columns per table, 10,000 rows per table, 20,000 rows and 100,000 cells overall, and 16 MiB of logical JSON. A state’s queries and final snapshot share one read transaction, providing a coherent view if another writer exists. Standalone snapshots also use one read transaction.

Differences report table additions/removals, schema changes and row addition/removal counts. An updated row counts as one removal and one addition. Suite reports retain identities, bounded query diagnostics and difference counts; they do not copy full database snapshots or seed data. Existing named-field and explicit-parameter redaction is applied to reports, including query row values. This is not a promise to infer every possible secret from arbitrary column names. Explicit standalone snapshot exports contain the selected database's actual values and must be treated as data files.

## Standalone commands

```sh
python3 -m reprolattice.sqlite_cli seed examples/inventory-seed.json inventory.sqlite
python3 -m reprolattice.sqlite_cli snapshot inventory.sqlite --output before.json
python3 -m reprolattice.sqlite_cli verify-snapshot before.json
python3 -m reprolattice.sqlite_cli compare before.json before.json
```

`check DATABASE CHECKS.json` runs a query-definition list. `compare BEFORE.json AFTER.json` checks snapshot integrity before comparing; it exits 1 for a valid difference, 0 for equality. Input/storage failures exit 2. Snapshot files use atomic create-only publication; no in-place database reset or deletion command is provided.

## Remaining work

Only SQLite is implemented here. PostgreSQL/MySQL, containerized providers, externally hosted test databases, migration orchestration, database-level sandboxing, full schema-equivalence rules and browser state inspection remain open. Run collections and full product scope remain open, as does the 20,000 useful production-SLOC acceptance.


## Python binding compatibility

Python 3.10 uses a permissive callback for internal authorizer reset because
`set_authorizer(None)` was added in Python 3.11. User-supplied queries still receive
the restrictive read-only function/operation policy, and inspection connections
remain query-only. VM/time, input and output budgets apply on every supported
version. Per-connection SQLite engine limits via `setlimit` additionally apply on
Python 3.11 and later; that binding is unavailable on Python 3.10. See the
[Python authorizer reference](https://docs.python.org/3.11/library/sqlite3.html#sqlite3.Connection.set_authorizer).
