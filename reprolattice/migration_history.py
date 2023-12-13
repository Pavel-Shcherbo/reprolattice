"""Protected, deterministic history committed with each isolated schema change."""

import json

from .migration_model import PREFIX
from .sqlite_seed import canonical, identity

STACK = PREFIX + "migration_stack"
EVENTS = PREFIX + "migration_events"


