"""Typed key-aware row differences with duplicate-preserving fallback and paging."""

from collections import Counter
import copy

from .sqlite_inspect import verify_database_snapshot
from .sqlite_seed import canonical, identity


def page_limits(offset, limit):
    if (
        type(offset) is not int
        or not 0 <= offset <= 40000
        or type(limit) is not int
        or not 1 <= limit <= 100
    ):
        raise ValueError("state pages require offset 0–40,000 and limit 1–100")


