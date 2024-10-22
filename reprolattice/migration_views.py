"""Phase-bound typed snapshot inspection and bounded portable rehearsal envelopes."""

import base64
import copy
import hashlib
from pathlib import Path
import re
import tempfile

from .jsonutil import strict_json
from .migration_bundle import inventory, verify_migration_bundle, FILES
from .migration_state import verify_migration_snapshot
from .sqlite_seed import canonical, identity
from .state_diff import table_page, compare_rows

MAX_EXPORT = 12 * 1024 * 1024


