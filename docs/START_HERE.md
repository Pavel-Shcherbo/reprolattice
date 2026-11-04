# Reproduce a retry failure

This walkthrough uses an isolated local HTTP fixture and a bundled synthetic inventory client. It needs Python 3.10 or later and a POSIX shell; the release controls are exercised on macOS arm64. There is no external inventory service and no account or API key.

## Install the preview

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install https://github.com/Pavel-Shcherbo/reprolattice/releases/download/v0.2.0/reprolattice-0.2.0-py3-none-any.whl
python -m reprolattice.resources ./demo
```

The [v0.2.0 release](https://github.com/Pavel-Shcherbo/reprolattice/releases/tag/v0.2.0) includes the wheel and `SHA256SUMS`. The exporter creates a new directory and refuses to overwrite an existing destination. Choose another destination if `demo` already exists. The application has no third-party runtime dependencies.

From a source checkout instead of a release, install with `python -m pip install .`, then export the same example directory.

## Catch the faulty client

```sh
python -m reprolattice check-client demo/retry.json --command python demo/inventory_client.py --faulty
```

An exit status of **1 is expected here**: this deliberately faulty client fails the scenario. Inspect the JSON checks rather than treating this command as an installation failure. The fixture first returns HTTP 503 and then HTTP 200 with `available: 7`. The faulty client does not complete the required retry.

## Check the corrected client

```sh
python -m reprolattice check-client demo/retry.json --command python demo/inventory_client.py
```

Expected: exit status **0**, `passed: true`, application output `{"available": 7}`, all interactions consumed and no unexpected requests. Each execution starts a fresh fixture server. These controls run a real subprocess over loopback HTTP rather than comparing a prepared screenshot.

## Inspect the same scenario visually

```sh
python -m reprolattice.web
```

Open http://127.0.0.1:8413. In **Verification target**, compare the faulty and corrected demo clients. The [README screenshots](../README.md#screenshots) show deliberately failing controls as well as retained evidence. For matrices and JUnit output, continue with [scenario suites](SUITES.md).

## Boundaries

Run trusted local commands only. The harness is not an operating-system sandbox. A successful HTTP interaction history alone does not prove correct database or queue side effects; use the explicit state/worker checks for those. Review reports for sensitive data before sharing.

Questions about this example belong in [Discussions](https://github.com/Pavel-Shcherbo/reprolattice/discussions). Include the exact command and a small synthetic fixture. See [assertion contracts](ASSERTIONS.md) for matching/output semantics.
