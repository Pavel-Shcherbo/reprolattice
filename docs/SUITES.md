# Scenario suites and CI reports

A suite runs trusted local applications against independent fixture servers and fresh per-case workspaces. It can also verify fixture transport without starting an application. Application verification and protocol verification are reported as separate modes.

## Run the control suite

```sh
python3 -m reprolattice.suites examples/inventory-suite.json --output .local/control-run --jobs 2
```

The bundled suite contains five expanded cases: three retry/quantity variants, one expected permission-denied outcome and one dynamic-path protocol check. Healthy clients pass all five. The workbench's **Use faulty retry client** control produces three failed retry variants and two passing cases. A failed application condition is not converted into an expected pass merely because the failure was deliberate.

For an installed package, first export reviewed examples:

```sh
python3 -m reprolattice.resources ./suite-demo
python3 -m reprolattice.suites suite-demo/inventory-suite.json --output .local/installed-control --jobs 2
```

Output directories must be new. Existing files or even an empty existing report directory are preserved and rejected. The output contains `report.json`, `junit.xml`, `report.html` and a hash manifest. A consumer should require a valid `manifest.json` and verify its file hashes before treating the set as complete. Report files are fsynced; directory metadata is not fsynced, so power-loss durability is not promised.

CLI exit codes are 0 for all selected cases passing, 1 for failed/error/incomplete selected execution, 2 for invalid input or report I/O, and 130 for an interrupted active run. Ctrl-C signals cancellation, stops running case processes and writes their cancellation results. An interrupt during configuration preflight can occur before a run/report exists.

## Suite definition

```json
{
  "version": 1,
  "name": "inventory-regression",
  "command": ["${python}", "inventory_client.py"],
  "cases": [{
    "id": "retry",
    "fixture": "retry.json",
    "tags": ["application", "retry"],
    "files": [{"path": "inventory_client.py"}]
  }]
}
```

Every case needs a unique bounded ASCII ID and a fixture, either an inline object or a root-relative JSON file. Optional `fixture_sha256` pins file bytes. Case fields override suite defaults for `command`, `mode` and `timeout`. The default mode is `application`; `protocol` cases require no command and need concrete `sample_request` values when request matchers are dynamic.

All cases and matrix variants are compiled before any case program starts. Preflight validates fixture contracts, application assertions, protocol samples, parameter references, file pins, paths and output assertions. A bad later case therefore prevents earlier program side effects. Unknown configuration fields are rejected.

## Typed parameter matrices

```json
{
  "id": "quantity",
  "matrix": {"available": [0, 7, 12]},
  "fixture": {
    "application": {"expected_json": {"available": {"$param": "available"}}},
    "interactions": [{
      "request": {"method": "GET", "path": "/inventory"},
      "response": {"json": {"available": {"$param": "available"}}}
    }]
  }
}
```

A sole `{"$param":"name"}` object preserves the full JSON value, including booleans, objects, arrays and null. `${name}` inside a string performs text interpolation of a non-null scalar. It does not evaluate Python, a shell expression or recursive templates. Interpolation in object keys is unsupported. Use a typed reference to carry a literal string containing template-like text.

`python` resolves to the current interpreter; `case_id` resolves to the expanded case ID. These names cannot be matrix dimensions. Matrix keys are traversed in sorted order; each dimension preserves its configured value order. IDs include an ordinal and parameter fingerprint so report order stays stable even when workers finish out of order. A matrix has at most six dimensions, 16 values per dimension and 64 combinations. Boolean `true` and number `1` remain distinct values.

## Workspace inputs and output artifacts

`files` lists explicit root-relative input files with optional SHA-256 pins. Contents are snapshotted during preflight and copied into each fresh workspace. Changes to source files after compilation do not silently alter that run. File paths cannot escape the root, and a file cannot overlap another file's directory path. No whole directory or repository tree is copied implicitly.

A case can declare output checks:

```json
{
  "artifacts": [{
    "path": "receipt.json",
    "kind": "json",
    "assertions": [{"path": "/available", "op": "equals", "value": 7}]
  }]
}
```

Supported artifact kinds are JSON and UTF-8 text. Rules use the same typed JSON-pointer assertion engine as application output. An optional `sha256` checks exact bytes. Missing files, malformed data, a wrong type, a hash mismatch or a failed assertion fail the case. Symbolic links are rejected; paths must remain inside the case workspace. Output records include size, hash and assertion results, without copying arbitrary output files into the report directory.

Workspaces are removed after the suite. Declared artifact contents are not retained as raw files; preserve a deliberate external copy in trusted application code if required. Case programs can still access resources outside their working directory and can make independent network calls. Workspace separation, output limits and process cleanup are not an operating-system sandbox.

## Status, cancellation and selection

| Status | Meaning |
|---|---|
| `passed` | Application/protocol checks and every declared artifact condition passed |
| `failed` | The program ran, but a condition, resource limit or case deadline failed |
| `error` | The case could not execute or an execution/inspection operation raised an error |
| `skipped` | Tag filtering excluded the case, or fail-fast prevented its start |
| `cancelled` | User cancellation or fail-fast stopped an in-flight selected case |

`--jobs` allows 1–8 concurrent cases. Submission is bounded to the active worker count. `--fail-fast` cancels in-flight cases and records not-started selected cases explicitly; it does not erase unsuccessful results. Case-result order follows suite definition/variant order. Operational start/finish events have a separate monotonically increasing sequence.

`--include-tag NAME` selects cases matching any included tag; `--exclude-tag NAME` removes cases matching any excluded tag. Both options can repeat. An empty selection is an error. Filtered cases remain visible as skipped; a successful partial selection has `full_suite: false` and a separate selected count.

Case `timeout` defaults to 10 seconds, at most 120. It covers workspace preparation, execution and inspection at the runner's cancellation checkpoints. Protocol cancellation is checked between local requests; an in-flight HTTP operation can take its socket timeout before returning. POSIX process groups are stopped, including child writers retaining pipes. Windows descendant cleanup is not qualified. The lower-level process collector caps stdout at 1 MiB and stderr at 256 KiB.

## Reports and identities

`definition_sha256` identifies suite JSON configuration. `suite_sha256` additionally identifies expanded fixtures, resolved commands/interpreter and all snapshotted input file hashes. Individual cases retain fixture, command and file hashes. Interpreter installation paths can change the execution identity across machines while preserving portable relative inputs and equivalent test outcomes.

JSON is the complete structured result. JUnit XML maps failures to `failure`, execution errors to `error` and cancelled/skipped cases to `skipped`, with cancellation also recorded in report counts/properties. Counts are validated against case records before export. HTML is a standalone escaped report with expandable details, no scripts and no external assets. Opening a report does not rerun a command.

JUnit consumers vary. The generated XML uses the testcase/classname/name, failure/error/skipped and per-test stderr elements described in [GitLab's unit-test report documentation](https://docs.gitlab.com/ci/testing/unit_test_reports/). No hosted CI run has been performed. A CI script must use this CLI's nonzero exit status; uploading XML alone does not determine job failure.

Application JSON output is represented by type/size/hash rather than copied raw. Value diagnostics are omitted when a case's diagnostic block exceeds its budget, while rule identities and pass/fail results remain. Such omission is marked; it is not a successful assertion.

## Redaction and limits

Named secret fields and known URL credentials are redacted. A case may declare `secret_parameters` naming string-valued matrix dimensions; their values are also replaced in retained free-text diagnostics. Structural enum fields and keys remain intact so reports stay machine-readable. Do not put secrets in field names or structural metadata. Hashes provide provenance, not anonymization, and short secret values can still be guessed from hashed inputs. This helper does not discover arbitrary sensitive application data.

Configuration is at most 2 MiB and 100 case definitions, expanding to at most 256 cases. Copied files have a 4 MiB individual/16 MiB per-file-set limit. Total loaded/expanded suite inputs are capped at 32 MiB; application/output-artifact assertion conditions are capped at 5,000. Each case has at most 16 declared artifacts, each read at most 1 MiB and at most 100 conditions. The combined exported report set is at most 64 MiB. These are bounded local workloads, not published throughput or formal memory-isolation guarantees.

The workbench runs only the reviewed bundled suite and supports 1, 2 or 4 workers. It does not accept arbitrary suite commands over HTTP. The CLI intentionally accepts trusted local application commands.

Workspace file entries now accept `role: "fixture"` (default) or `role: "subject"`. Both remain pinned and isolated; the role determines which changes a run comparison treats as test conditions versus program changes. Reports also retain original runner context and parameter/artifact-contract fingerprints. See RUNS.md for archive, identity and baseline semantics.
