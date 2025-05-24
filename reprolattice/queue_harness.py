"""Run a real trusted worker and reconcile process, queue and replay assertions."""

import os
import threading

from .assertions import evaluate_rules, json_equal
from .jsonutil import strict_json
from .process import run_process
from .queue_engine import verify_queue_evidence
from .queue_http import make_queue_server
from .queue_model import fixture_contract
from .redaction import redact


def check_queue(fixture, command, timeout=10, cwd=None, should_cancel=None):
    config, expected, rules, exit_code, queue_rules = fixture_contract(fixture)
    server, engine, capability, wire = make_queue_server(config)
    thread = threading.Thread(
        target=lambda: server.serve_forever(poll_interval=0.02), daemon=True
    )
    thread.start()
    env = {
        key: os.environ[key]
        for key in ("PATH", "SYSTEMROOT", "WINDIR", "TMPDIR")
        if key in os.environ
    }
    env["REPROLATTICE_QUEUE_URL"] = f"http://127.0.0.1:{server.server_port}/command"
    env["REPROLATTICE_QUEUE_CAPABILITY"] = capability
    try:
        process = run_process(
            command, env=env, cwd=cwd, timeout=timeout, should_cancel=should_cancel
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    try:
        output = strict_json(process.stdout)
        valid_json = process.stdout_valid_utf8
    except ValueError:
        output, valid_json = None, False
    evidence = engine.evidence(wire_errors=wire["errors"])
    replay = verify_queue_evidence(evidence)
    app_assertions = evaluate_rules(output, rules) if valid_json else []
    queue_assertions = evaluate_rules(evidence["state"], queue_rules)
    checks = {
        "exit_status": process.returncode == exit_code,
        "application_output": valid_json
        and (
            "expected_json" not in expected
            or json_equal(output, expected["expected_json"])
        ),
        "application_assertions": valid_json
        and all(item["passed"] for item in app_assertions),
        "queue_assertions": all(item["passed"] for item in queue_assertions),
        "expected_rejections": engine.rejections
        == fixture.get("expected_rejections", 0),
        "no_wire_errors": wire["errors"] == 0,
        "complete_command_history": evidence["complete"],
        "fresh_queue_replay": replay["passed"] and replay["complete"],
        "within_time_limit": not process.timed_out,
        "within_output_limit": not process.output_limited,
        "not_cancelled": not process.cancelled,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "application": {
            "returncode": process.returncode,
            "output": redact(output),
            "stderr": process.stderr[-8192:],
        },
        "assertions": app_assertions,
        "queue_assertions": queue_assertions,
        "queue_evidence": evidence,
        "queue": {
            "clock": engine.clock,
            "message_count": len(engine.messages),
            "deliveries": engine.deliveries,
            "counts": evidence["state"]["counts"],
            "commands": len(engine.journal),
            "rejected_commands": engine.rejections,
            "wire_errors": wire["errors"],
            "accepted_connections": wire["accepted"],
            "event_head": engine.head,
        },
        "cancelled": process.cancelled,
    }
