"""Run a trusted test client against a temporary fixture dependency."""

import json
import os
import signal
import subprocess
import threading

from .replay import make_server


def check_client(fixture, command, timeout=10, cwd=None):
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
    expected = fixture.get("application")
    if not isinstance(expected, dict) or "expected_json" not in expected:
        raise ValueError("fixture.application.expected_json is required")
    server, state = make_server(fixture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env = {
        key: os.environ[key]
        for key in ["PATH", "SYSTEMROOT", "WINDIR", "TMPDIR"]
        if key in os.environ
    }
    env["REPROLATTICE_BASE_URL"] = f"http://127.0.0.1:{server.server_port}"
    try:
        with subprocess.Popen(
            command,
            env=env,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=(os.name == "posix"),
        ) as process:
            try:
                stdout, stderr = process.communicate(timeout=timeout)
                returncode, timed_out = process.returncode, False
            except subprocess.TimeoutExpired:
                try:
                    if os.name == "posix":
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                except ProcessLookupError:
                    pass
                stdout, stderr = process.communicate()
                returncode, timed_out = process.returncode, True
                stderr += "\nclient exceeded time limit"
        try:
            output = json.loads(stdout)
            valid_json = True
        except ValueError:
            output, valid_json = None, False
        checks = {
            "exit_status": returncode == expected.get("expected_exit", 0),
            "application_output": valid_json and output == expected["expected_json"],
            "all_interactions_consumed": state["consumed"] == state["total"],
            "no_unexpected_requests": state["unexpected"] == 0,
            "within_time_limit": not timed_out,
        }
        return {
            "passed": all(checks.values()),
            "checks": checks,
            "application": {
                "returncode": returncode,
                "output": output,
                "stderr": stderr[-8192:],
            },
            **state,
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
