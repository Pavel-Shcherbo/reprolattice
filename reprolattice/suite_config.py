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


def read_bounded(path, maximum):
    with Path(path).open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError("suite input exceeds its byte budget")
    return raw


@dataclass(frozen=True)
class FileInput:
    path: str
    content: bytes
    sha256: str


@dataclass(frozen=True)
class ArtifactRule:
    path: str
    kind: str
    rules: tuple
    sha256: object


@dataclass(frozen=True)
class SuiteCase:
    id: str
    source_id: str
    tags: tuple
    parameters: dict
    secrets: tuple
    fixture: dict
    fixture_sha256: str
    command: tuple
    mode: str
    timeout: float
    files: tuple
    artifacts: tuple


@dataclass(frozen=True)
class SuitePlan:
    name: str
    definition_sha256: str
    snapshot_sha256: str
    cases: tuple
    input_bytes: int


def compile_files(definitions, root):
    if not isinstance(definitions, list) or len(definitions) > 32:
        raise ValueError("workspace files must contain at most 32 entries")
    files, names, size = [], set(), 0
    for definition in definitions:
        if (
            not isinstance(definition, dict)
            or set(definition) - {"path", "sha256"}
            or "path" not in definition
        ):
            raise ValueError("workspace file requires path and optional sha256")
        name = relative_path(definition["path"])
        canonical_name = str(Path(name))
        if canonical_name in names:
            raise ValueError("workspace input paths must be unique")
        names.add(canonical_name)
        source = rooted(root, name)
        if not source.is_file():
            raise ValueError("workspace input must be a regular file")
        raw = read_bounded(source, 4 * 1024 * 1024)
        size += len(raw)
        if size > 16 * 1024 * 1024:
            raise ValueError("workspace inputs exceed 16 MiB")
        actual = hashlib.sha256(raw).hexdigest()
        if "sha256" in definition and (
            not isinstance(definition["sha256"], str)
            or not SHA.fullmatch(definition["sha256"])
            or definition["sha256"] != actual
        ):
            raise ValueError("workspace input differs from its pinned SHA-256")
        files.append(FileInput(name, raw, actual))
    for left in names:
        if any(left != right and Path(left) in Path(right).parents for right in names):
            raise ValueError(
                "workspace file paths cannot overlap as file and directory"
            )
    return tuple(files)


