"""Immutable migration rehearsal contracts with explicit checks and reverse SQL."""

import copy
from dataclasses import dataclass

from .jsonutil import validate_json
from .sqlite_inspect import compile_queries
from .sqlite_seed import canonical, identity, name, sqlite_value

MAX_PLAN = 4 * 1024 * 1024
PREFIX = "_reprolattice_"


@dataclass(frozen=True)
class MigrationPlan:
    definition: dict
    sha256: str


