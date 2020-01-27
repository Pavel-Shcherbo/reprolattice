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
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    output_limited: bool
    stdout_valid_utf8: bool


def stop_process(process):
    """Kill the POSIX process group, including descendants after the leader exits."""
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        elif process.poll() is None:
            process.kill()
    except ProcessLookupError:
        pass


