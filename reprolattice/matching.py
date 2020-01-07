"""Bounded request matching for ordered HTTP scenarios."""

import copy
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from .assertions import compile_rules, json_equal
from .jsonutil import validate_json

METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


