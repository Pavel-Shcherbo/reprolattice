"""Run only the reviewed bundled suite through the loopback workbench."""

import json
from .reports import junit_xml
from .resources import examples_directory
from .suite_config import compile_suite
from .suite_runner import run_suite


def evaluate_suite(params):
    if set(params) - {"mode", "jobs", "faulty_client"}:
        raise ValueError(
            "suite workbench accepts only jobs and the bundled faulty-client control"
        )
    jobs = params.get("jobs", 2)
    if type(jobs) is not int or jobs not in (1, 2, 4):
        raise ValueError("workbench suite jobs must be one, two or four")
    if type(params.get("faulty_client", False)) is not bool:
        raise ValueError("faulty_client must be boolean")
    directory = examples_directory()
    definition = json.loads((directory / "inventory-suite.json").read_text())
    if params.get("faulty_client"):
        definition["command"].append("--faulty")
    report = run_suite(compile_suite(definition, directory), jobs=jobs)
    return {"mode": "suite", "report": report, "junit_xml": junit_xml(report).decode()}
