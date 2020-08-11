"""Run a trusted test client against a temporary fixture dependency."""

import os
import threading

from .replay import make_server
from .assertions import compile_rules, evaluate_rules, json_equal
from .jsonutil import strict_json
from .redaction import redact
from .process import run_process


def application_contract(fixture):
    if not isinstance(fixture, dict):
        raise ValueError("fixture must be an object")
    expected = fixture.get("application")
    if not isinstance(expected, dict) or (
        "expected_json" not in expected and not expected.get("assertions")
    ):
        raise ValueError("application requires expected_json or non-empty assertions")
    rules = compile_rules(expected.get("assertions", []))
    expected_exit = expected.get("expected_exit", 0)
    if type(expected_exit) is not int or not -255 <= expected_exit <= 255:
        raise ValueError("expected_exit must be an integer between -255 and 255")
    if set(expected) - {"expected_json", "expected_exit", "assertions"}:
        raise ValueError("application contract contains unsupported fields")
    return expected, rules, expected_exit


def check_client(fixture, command, timeout=10, cwd=None, should_cancel=None):
    if not isinstance(fixture, dict):
        raise ValueError("fixture must be an object")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(arg, str) and arg for arg in command)
    ):
        raise ValueError("command must be a non-empty argument list")
    if type(timeout) not in (int, float) or not 0 < timeout <= 120:
        raise ValueError("timeout must be between 0 and 120 seconds")
    if should_cancel is not None and not callable(should_cancel):
        raise ValueError("should_cancel must be callable")
    expected, rules, expected_exit = application_contract(fixture)
    server, state = make_server(fixture)
    thread = threading.Thread(
        target=lambda: server.serve_forever(poll_interval=0.05), daemon=True
    )
    thread.start()
    env = {
        key: os.environ[key]
        for key in ["PATH", "SYSTEMROOT", "WINDIR", "TMPDIR"]
        if key in os.environ
    }
    env["REPROLATTICE_BASE_URL"] = f"http://127.0.0.1:{server.server_port}"
    try:
        process = run_process(
            command, env=env, cwd=cwd, timeout=timeout, should_cancel=should_cancel
        )
        stdout, stderr = process.stdout, process.stderr
        if process.timed_out:
            stderr += "\nclient exceeded time limit"
        if process.output_limited:
            stderr += "\nclient exceeded output limit"
        try:
            output = strict_json(stdout)
            valid_json = process.stdout_valid_utf8
        except ValueError:
            output, valid_json = None, False
        assertions = evaluate_rules(output, rules) if valid_json else []
        checks = {
            "exit_status": process.returncode == expected_exit,
            "application_output": valid_json
            and (
                "expected_json" not in expected
                or json_equal(output, expected["expected_json"])
            ),
            "application_assertions": valid_json
            and all(item["passed"] for item in assertions),
            "all_interactions_consumed": state["consumed"] == state["total"],
            "no_unexpected_requests": state["unexpected"] == 0,
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
                "stderr": stderr[-8192:],
            },
            "assertions": assertions,
            "cancelled": process.cancelled,
            **state,
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
