"""Bounded JSON parameter expansion without evaluation or shell interpolation."""

import copy
import hashlib
import itertools
import json
import re

from .jsonutil import validate_json
from .redaction import redact

NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,47}$")
TOKEN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]{0,47})\}")


