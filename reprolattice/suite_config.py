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
from .queue_model import fixture_contract

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
    role: str = "fixture"


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
    states: tuple = ()


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
            or set(definition) - {"path", "sha256", "role"}
            or "path" not in definition
        ):
            raise ValueError("workspace file requires path and optional sha256/role")
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
        role = definition.get("role", "fixture")
        if role not in ("fixture", "subject"):
            raise ValueError("workspace file role must be fixture or subject")
        files.append(FileInput(name, raw, actual, role))
    for left in names:
        if any(left != right and Path(left) in Path(right).parents for right in names):
            raise ValueError(
                "workspace file paths cannot overlap as file and directory"
            )
    return tuple(files)


def compile_artifacts(definitions):
    if not isinstance(definitions, list) or len(definitions) > 16:
        raise ValueError("case artifacts must contain at most 16 entries")
    result, seen = [], set()
    for item in definitions:
        if (
            not isinstance(item, dict)
            or set(item) - {"path", "kind", "assertions", "sha256"}
            or not {"path", "kind"} <= set(item)
        ):
            raise ValueError(
                "artifact requires path, kind and optional assertions/hash"
            )
        path = relative_path(item["path"])
        if str(Path(path)) in seen:
            raise ValueError("artifact paths must be unique")
        seen.add(str(Path(path)))
        kind = item["kind"]
        if kind not in ("json", "text"):
            raise ValueError("artifact kind must be json or text")
        rules = compile_rules(item.get("assertions", []))
        if len(rules) > 100:
            raise ValueError("artifact supports at most 100 conditions")
        expected_hash = item.get("sha256")
        if expected_hash is not None and (
            not isinstance(expected_hash, str) or not SHA.fullmatch(expected_hash)
        ):
            raise ValueError("artifact SHA-256 must be lowercase hexadecimal")
        result.append(ArtifactRule(path, kind, rules, expected_hash))
    return tuple(result)


def compile_suite(definition, root="."):
    validate_json(definition, max_bytes=2 * 1024 * 1024, max_depth=50, max_nodes=100000)
    allowed = {"version", "name", "command", "mode", "timeout", "cases"}
    if (
        not isinstance(definition, dict)
        or set(definition) - allowed
        or type(definition.get("version")) is not int
        or definition.get("version") != 1
    ):
        raise ValueError("suite requires version 1 and supported fields")
    name = named(definition.get("name"), "suite name")
    cases = definition.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 100:
        raise ValueError("suite requires 1–100 case definitions")
    result, ids, input_bytes, total_rules = [], set(), 0, 0
    cached_files = {}
    expanded_ids = set()
    for case in cases:
        allowed_case = {
            "id",
            "fixture",
            "fixture_sha256",
            "command",
            "mode",
            "timeout",
            "tags",
            "matrix",
            "secret_parameters",
            "files",
            "artifacts",
            "sqlite",
        }
        if not isinstance(case, dict) or set(case) - allowed_case:
            raise ValueError("suite case contains unsupported fields")
        source_id = named(case.get("id"), "case ID")
        if source_id in ids:
            raise ValueError("case IDs must be unique")
        ids.add(source_id)
        tags = case.get("tags", [])
        if (
            not isinstance(tags, list)
            or len(tags) > 20
            or any(not isinstance(tag, str) for tag in tags)
            or len(set(tags)) != len(tags)
        ):
            raise ValueError("case tags must be a unique list of at most 20 labels")
        for tag in tags:
            named(tag, "tag")
        secret_names = case.get("secret_parameters", [])
        if not isinstance(secret_names, list) or len(secret_names) > 6:
            raise ValueError("secret_parameters must be a bounded name list")
        for parameter in secret_names:
            parameter_name(parameter)
        matrix = variants(case.get("matrix", {}))
        fixture_source = case.get("fixture")
        if isinstance(fixture_source, str):
            raw = read_bounded(rooted(root, fixture_source), 2 * 1024 * 1024)
            input_bytes += len(raw)
            expected_hash = case.get("fixture_sha256")
            if expected_hash is not None and (
                not isinstance(expected_hash, str)
                or not SHA.fullmatch(expected_hash)
                or hashlib.sha256(raw).hexdigest() != expected_hash
            ):
                raise ValueError("fixture file differs from its pinned SHA-256")
            fixture_template = strict_json(raw, max_bytes=2 * 1024 * 1024)
        elif isinstance(fixture_source, dict):
            if "fixture_sha256" in case:
                raise ValueError("fixture_sha256 is supported only for file fixtures")
            fixture_template = fixture_source
        else:
            raise ValueError(
                "case fixture must be a relative filename or inline object"
            )
        for index, parameters in enumerate(matrix, 1):
            if len(result) >= 256:
                raise ValueError("expanded suite exceeds 256 cases")
            case_id = source_id + (
                "-" + str(index).zfill(3) + "-" + variant_identity(parameters)
                if case.get("matrix")
                else ""
            )
            if case_id in expanded_ids:
                raise ValueError("expanded case IDs collide")
            expanded_ids.add(case_id)
            runtime = {**parameters, "python": sys.executable, "case_id": case_id}
            secret_values = []
            for secret_name in secret_names:
                value = parameters.get(secret_name)
                if not isinstance(value, str) or not 1 <= len(value) <= 4096:
                    raise ValueError(
                        "secret parameters require explicit non-empty string matrix values"
                    )
                secret_values.append(value)
            fixture = expand(fixture_template, runtime)
            mode = case.get("mode", definition.get("mode", "application"))
            if mode not in ("application", "protocol", "queue"):
                raise ValueError("case mode must be application, protocol or queue")
            if mode == "queue":
                if secret_names:
                    raise ValueError(
                        "queue evidence requires synthetic inputs without secret_parameters"
                    )
                _, _, _, _, queue_rules = fixture_contract(fixture)
                total_rules += len(queue_rules)
            else:
                validate(fixture)
            command = expand(
                case.get("command", definition.get("command", [])), runtime
            )
            if mode in ("application", "queue"):
                if (
                    not isinstance(command, list)
                    or not command
                    or not all(
                        isinstance(argument, str)
                        and argument
                        and "\x00" not in argument
                        for argument in command
                    )
                ):
                    raise ValueError(
                        "application case requires a non-empty command argument list"
                    )
                if sum(len(argument.encode()) for argument in command) > 65536:
                    raise ValueError("case command exceeds 64 KiB")
                _, rules, _ = application_contract(fixture)
                total_rules += len(rules)
            else:
                if command:
                    raise ValueError(
                        "protocol cases cannot declare an application command"
                    )
                for interaction in fixture["interactions"]:
                    sample_request(interaction)
            timeout = case.get("timeout", definition.get("timeout", 10))
            if (
                type(timeout) not in (int, float)
                or not math.isfinite(timeout)
                or not 0 < timeout <= 120
            ):
                raise ValueError(
                    "case timeout must be finite and between 0 and 120 seconds"
                )
            file_definitions = expand(case.get("files", []), runtime)
            cache_key = json.dumps(file_definitions, sort_keys=True)
            if cache_key not in cached_files:
                files = compile_files(file_definitions, root)
                cached_files[cache_key] = files
                input_bytes += sum(len(file.content) for file in files)
            files = cached_files[cache_key]
            artifacts = compile_artifacts(expand(case.get("artifacts", []), runtime))
            from .sqlite_state import compile_states

            states = compile_states(expand(case.get("sqlite", []), runtime), root)
            input_bytes += sum(state.input_bytes for state in states)
            total_rules += sum(len(state.queries) for state in states)
            paths = [str(Path(file.path)).casefold() for file in files] + [
                str(Path(state.path)).casefold() for state in states
            ]
            if len(set(paths)) != len(paths) or any(
                left != right and Path(left) in Path(right).parents
                for left in paths
                for right in paths
            ):
                raise ValueError(
                    "SQLite state paths and workspace files cannot overlap"
                )
            for state in states:
                for suffix in ("-wal", "-shm", "-journal"):
                    reserved = Path(str(Path(state.path)).casefold() + suffix)
                    if any(
                        reserved == Path(path)
                        or reserved in Path(path).parents
                        or Path(path) in reserved.parents
                        for path in paths
                    ):
                        raise ValueError(
                            "SQLite sidecar paths cannot overlap workspace inputs or states"
                        )
            total_rules += sum(len(artifact.rules) for artifact in artifacts)
            if total_rules > 5000 or input_bytes > 32 * 1024 * 1024:
                raise ValueError(
                    "suite exceeds its total assertion or source byte budget"
                )
            fixture_bytes = json.dumps(
                fixture, sort_keys=True, separators=(",", ":")
            ).encode()
            input_bytes += len(fixture_bytes)
            if total_rules > 5000 or input_bytes > 32 * 1024 * 1024:
                raise ValueError(
                    "suite exceeds its total assertion or source byte budget"
                )
            result.append(
                SuiteCase(
                    case_id,
                    source_id,
                    tuple(tags),
                    copy.deepcopy(parameters),
                    tuple(secret_values),
                    copy.deepcopy(fixture),
                    hashlib.sha256(fixture_bytes).hexdigest(),
                    tuple(command),
                    mode,
                    timeout,
                    files,
                    artifacts,
                    states,
                )
            )
    fingerprint = hashlib.sha256(
        json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    snapshot = {
        "definition_sha256": fingerprint,
        "cases": [
            {
                "id": item.id,
                "fixture_sha256": item.fixture_sha256,
                "command": item.command,
                "files": [(file.path, file.sha256, file.role) for file in item.files],
                "sqlite": [(state.path, state.sha256) for state in item.states],
            }
            for item in result
        ],
    }
    snapshot_hash = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return SuitePlan(name, fingerprint, snapshot_hash, tuple(result), input_bytes)
