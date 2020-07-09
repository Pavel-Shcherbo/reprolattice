"""Inspect declared case outputs without copying arbitrary application files."""

import hashlib
from pathlib import Path

from .assertions import evaluate_rules
from .jsonutil import strict_json
from .suite_config import rooted, read_bounded


def check_artifacts(workspace, definitions):
    results = []
    workspace = Path(workspace).resolve()
    for definition in definitions:
        report = {"path": definition.path, "kind": definition.kind, "passed": False}
        try:
            lexical = workspace / definition.path
            if any(
                part.is_symlink()
                for part in [lexical, *lexical.parents]
                if part.is_relative_to(workspace)
            ):
                raise ValueError("artifact symlinks are unsupported")
            target = rooted(workspace, definition.path)
            if not target.is_file():
                raise ValueError(
                    "declared artifact is missing or is not a regular file"
                )
            raw = read_bounded(target, 1024 * 1024)
            actual_hash = hashlib.sha256(raw).hexdigest()
            value = (
                strict_json(raw) if definition.kind == "json" else raw.decode("utf-8")
            )
            assertions = evaluate_rules(value, definition.rules)
            hash_passed = definition.sha256 is None or actual_hash == definition.sha256
            report.update(
                sha256=actual_hash,
                bytes=len(raw),
                assertions=assertions,
                hash_passed=hash_passed,
                passed=hash_passed and all(rule["passed"] for rule in assertions),
            )
        except (ValueError, OSError) as error:
            report["error"] = str(error)
        results.append(report)
    return results
