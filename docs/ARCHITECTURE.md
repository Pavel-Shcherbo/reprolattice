# Architecture

## Current implementation

Fixture validation creates a private interaction list. A lock protects its sequence cursor. Each matching request consumes one expected interaction; a mismatch leaves the cursor unchanged and increments the unexpected counter. The server binds to loopback and has no upstream target. The workbench starts a temporary fixture server, sends control requests, closes it and reports the observed responses.

## Verification

Ordered failure/recovery responses, body mismatches, unknown paths, extra calls, recursive redaction, invalid headers and malformed fixtures; the faulty client fails and the corrected client passes the same scenario.

## Local HTTP boundary

The workbench binds to loopback, validates the Host header, rejects foreign
Origin values and requires a custom header for state-changing requests. Static
files are served from an explicit allowlist. Request bodies are limited to 1 MiB.
These measures support a local development tool; there is no production identity,
authorization or organization model yet.

## Next architectural increment

Add portable application-state assertions and process-tree cleanup, then introduce explicit local capture with reviewed redaction policies.
