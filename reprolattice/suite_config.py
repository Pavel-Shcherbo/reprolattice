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


