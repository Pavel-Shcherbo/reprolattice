"""Bounded pipe collection and deadline enforcement for trusted local programs."""

import math
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessResult:
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool
    output_limited: bool
    stdout_valid_utf8: bool
    cancelled: bool = False


def stop_process(process):
    """Kill the POSIX process group, including descendants after the leader exits."""
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        elif process.poll() is None:
            process.kill()
    except ProcessLookupError:
        pass
    except PermissionError as error:
        # macOS can retire a group just before waitpid observes its leader's exit.
        # Confirm that exact child's exit; never hide failure for a live leader.
        if process.poll() is None:
            try:
                process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                raise error from None


def run_process(
    command,
    *,
    env,
    cwd=None,
    timeout=10,
    stdout_limit=1024 * 1024,
    stderr_limit=256 * 1024,
    should_cancel=None,
):
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(arg, str) and arg for arg in command)
    ):
        raise ValueError("command must be a non-empty argument list")
    if (
        type(timeout) not in (int, float)
        or not math.isfinite(timeout)
        or not 0 < timeout <= 120
    ):
        raise ValueError("timeout must be finite and between 0 and 120 seconds")
    if any(
        type(limit) is not int or not 1 <= limit <= 16 * 1024 * 1024
        for limit in (stdout_limit, stderr_limit)
    ):
        raise ValueError("stream limits must be integers between 1 byte and 16 MiB")
    if should_cancel is not None and not callable(should_cancel):
        raise ValueError("should_cancel must be callable")
    if should_cancel is not None and should_cancel():
        return ProcessResult(None, "", "", False, False, True, True)
    buffers = [bytearray(), bytearray()]
    finished = [threading.Event(), threading.Event()]
    exceeded = threading.Event()
    failures = []

    def collect(stream, index, limit):
        try:
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    break
                remaining = limit - len(buffers[index])
                buffers[index].extend(chunk[:remaining])
                if len(chunk) > remaining:
                    exceeded.set()
        except (OSError, ValueError) as error:
            failures.append(type(error).__name__)
        finally:
            finished[index].set()

    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        start_new_session=(os.name == "posix"),
    )
    readers = [
        threading.Thread(target=collect, args=(stream, index, limit), daemon=True)
        for index, (stream, limit) in enumerate(
            ((process.stdout, stdout_limit), (process.stderr, stderr_limit))
        )
    ]
    deadline = time.monotonic() + timeout
    timed_out = False
    cancelled = False
    try:
        for reader in readers:
            reader.start()
        while True:
            if should_cancel is not None and should_cancel():
                cancelled = True
                stop_process(process)
                break
            if exceeded.is_set():
                stop_process(process)
                break
            if process.poll() is not None and all(event.is_set() for event in finished):
                break
            if time.monotonic() >= deadline:
                timed_out = True
                stop_process(process)
                break
            time.sleep(min(0.01, max(0, deadline - time.monotonic())))
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            stop_process(process)
            process.wait(timeout=1)
        for reader in readers:
            reader.join(timeout=0.5)
        # Raw unbuffered pipes can be closed even when a descendant retains its writer.
        process.stdout.close()
        process.stderr.close()
        if failures and not timed_out and not exceeded.is_set() and not cancelled:
            raise RuntimeError("application output collection failed")
        try:
            stdout = buffers[0].decode("utf-8")
            valid_utf8 = True
        except UnicodeDecodeError:
            stdout, valid_utf8 = buffers[0].decode("utf-8", errors="replace"), False
        return ProcessResult(
            process.returncode,
            stdout,
            buffers[1].decode("utf-8", errors="replace"),
            timed_out,
            exceeded.is_set(),
            valid_utf8,
            cancelled,
        )
    finally:
        stop_process(process)
        process.stdout.close()
        process.stderr.close()
        if process.poll() is None:
            process.wait(timeout=1)
