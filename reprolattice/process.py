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


