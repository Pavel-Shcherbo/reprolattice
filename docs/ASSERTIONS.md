# Request rules and application assertions

Fixtures remain ordered. A mismatch returns HTTP 409, increments `unexpected` and does not consume the next interaction. No upstream request is made.

## Request matching

A request requires `method` and exactly one of `path` or `path_pattern`. Exact paths preserve raw query encoding. A pattern matches only the URL path component, using `*` for zero or more characters (including `/`) and `?` for one character; it is not a regular expression. Absolute URLs and network paths are rejected.

`headers` specifies an exact subset with case-insensitive names and case-sensitive values. Additional headers are allowed. Duplicate actual header values are retained as arrays. `header_assertions` uses lowercase names in pointers.

`json` specifies the complete typed JSON body. `json_assertions` checks selected parts instead; both can be used together. `query_assertions` exposes decoded query parameters, preserving repeated values as arrays and blank values as empty strings. When query assertions are present, an exact `path` excludes the query. Without query assertions, a path pattern leaves the query unrestricted.

For CLI or workbench protocol verification, dynamic rules require a concrete interaction-level `sample_request` containing `method`, `path`, optional `headers` and optional `json`. The sample is checked against its matcher before any server is started. It is then sent over real loopback HTTP. Application clients supply their own requests and do not need samples. See `examples/dynamic-order.json`.

## Application output

`application.expected_json` preserves complete-output checking. Alternatively, define a non-empty `application.assertions` list. When both are present, both must pass. Assertions do not execute expressions or user code.

```json
{
  "application": {
    "assertions": [
      {"id": "reference", "path": "/order/id", "op": "type", "value": "string"},
      {"id": "total", "path": "/total", "op": "approx", "value": 100, "atol": 0.01, "rtol": 0},
      {"id": "accepted", "path": "/accepted", "op": "equals", "value": true}
    ]
  }
}
```

Pointers use an empty string for the root, `/` for an empty property name, `~0` for a literal `~` and `~1` for a literal `/`. Array indices are decimal without leading zeros. Missing fields differ from JSON null.

| Operation | Meaning |
|---|---|
| `exists`, `absent` | Presence check; no `value` accepted |
| `equals`, `not_equals` | Complete typed equality; boolean `true` differs from number `1` |
| `type` | `null`, `boolean`, `number`, `integer`, `string`, `array`, `object` |
| `contains` | String substring or typed array membership |
| `subset` | Recursive object subset; arrays remain exact |
| `one_of` | Typed equality to one of 1–100 alternatives |
| `gt`, `gte`, `lt`, `lte` | Numeric comparisons without string coercion |
| `approx` | `abs(actual - expected) <= atol + rtol * abs(expected)` |

Approximate comparison defaults to `atol=1e-9`, `rtol=1e-6`. Explicit tolerances are recommended for domain quantities. Decimal arithmetic avoids overflow in tolerance calculations; operands must still be finite and float-representable. Whole-number floats satisfy the `integer` type.

Rule IDs must be unique within a rule list. Unknown fields, operations and invalid pointers fail validation before starting the application. Rules are limited to 1,000 per list, pointers to 50 components and operands to 256 KiB. JSON is finite, depth-bounded and rejects duplicate object keys. Application stdout collection is capped at 1 MiB and stderr at 256 KiB; exceeding either budget stops the process and fails `within_output_limit`. UTF-8 errors in stdout cannot pass output validation. The deadline includes draining inherited pipes after the process leader exits. POSIX runs stop the process group; Windows stops the immediate process only and has not been qualified. Run trusted commands only: these limits are not an operating-system sandbox.

Reports include each condition's result and bounded diagnostic values. Named secret fields and values below secret-named pointer ancestors are redacted. This is a name-based helper, not comprehensive secret detection; process stderr and arbitrary user-selected IDs or paths require review before sharing.
