"""Preflight all suite variants, fixture contracts and isolated workspace inputs."""

import copy
import hashlib
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .assertions import compile_rules
from .harness import application_contract
from .jsonutil import strict_json, validate_json
from .parameters import expand, variants, parameter_name, variant_identity
from .protocol import sample_request
from .replay import validate

ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
SHA = re.compile(r"^[0-9a-f]{64}$")


def named(value, label):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError(f"{label} must be a bounded ASCII identifier")
    return value


def relative_path(value):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 512
        or "\\" in value
        or "\x00" in value
    ):
        raise ValueError("suite paths must use bounded relative forward-slash names")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path == Path("."):
        raise ValueError("suite path must stay within its workspace")
    return value


def rooted(root, relative):
    relative_path(relative)
    root = Path(root).resolve()
    target = root.joinpath(relative).resolve()
    if not target.is_relative_to(root):
        raise ValueError("suite path escapes its root through a symlink")
    return target


