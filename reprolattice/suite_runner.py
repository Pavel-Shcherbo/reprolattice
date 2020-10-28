"""Bounded concurrent suite execution with deterministic result ordering."""

import hashlib
import json
import tempfile
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path

from .artifact_checks import check_artifacts
from .harness import check_client
from .parameters import scrub
from .protocol import verify_protocol
from .suite_config import SuitePlan, named


def utc_now():
    return datetime.now(timezone.utc).isoformat()


