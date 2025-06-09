"""Run queue-backed application fixtures and verify retained broker evidence."""

import argparse
import json
import os
from pathlib import Path
import tempfile

from .jsonutil import strict_json
from .queue_engine import verify_queue_evidence
from .queue_harness import check_queue
from .queue_model import canonical, MAX_EVIDENCE


