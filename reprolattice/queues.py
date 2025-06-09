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


def write_evidence(document, path):
    verify_queue_evidence(document)
    raw = canonical(document) + b"\n"
    if len(raw) > MAX_EVIDENCE:
        raise ValueError("queue evidence exceeds 8 MiB")
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".queue-proof-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"path": str(path), "sha256": document["sha256"], "bytes": len(raw)}


