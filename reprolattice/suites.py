"""Execute a trusted local scenario suite and retain reviewable CI reports."""

import argparse
import json
import signal
import threading
from pathlib import Path

from .jsonutil import strict_json
from .reports import write_reports
from .suite_config import compile_suite, read_bounded
from .suite_runner import run_suite


