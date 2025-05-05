"""Linearized virtual-clock deliveries, fenced acknowledgements and replay journal."""

import copy
import threading

from .jsonutil import validate_json
from .queue_model import (
    canonical,
    configuration,
    fields,
    fingerprint,
    integer,
    name,
    MAX_EVIDENCE,
)


class QueueCapacity(ValueError):
    pass


class QueueEngine:
    pass
