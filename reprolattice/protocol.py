"""Verify fixture transport with explicit concrete examples for dynamic matchers."""

import copy
import http.client
import json
import threading

from .assertions import json_equal
from .jsonutil import strict_json
from .matching import compile_request
from .redaction import redact
from .replay import make_server, validate


def sample_request(item):
    definition = item["request"]
    sample = item.get("sample_request")
    dynamic = any(
        key in definition
        for key in (
            "path_pattern",
            "json_assertions",
            "query_assertions",
            "header_assertions",
        )
    )
    if sample is None:
        if dynamic:
            raise ValueError(
                "dynamic request rules require sample_request for protocol verification"
            )
        sample = copy.deepcopy(definition)
    if not isinstance(sample, dict) or set(sample) - {
        "method",
        "path",
        "headers",
        "json",
    }:
        raise ValueError("sample_request supports only method, path, headers and json")
    compile_request(sample)
    issues = compile_request(definition).match(
        sample["method"], sample["path"], sample.get("json"), sample.get("headers", {})
    )
    if issues:
        raise ValueError("sample_request does not satisfy its request matcher")
    return sample


def verify_protocol(fixture, inject_mismatch=False):
    interactions = validate(fixture)
    samples = [sample_request(item) for item in interactions]
    server, state = make_server(fixture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    results = []
    try:
        for item, request in zip(interactions, samples):
            path = (
                "/unexpected-test-path"
                if inject_mismatch and not results
                else request["path"]
            )
            connection = http.client.HTTPConnection(
                "127.0.0.1", server.server_port, timeout=3
            )
            try:
                body = json.dumps(request["json"]) if "json" in request else None
                connection.request(
                    request["method"], path, body, headers=request.get("headers", {})
                )
                response = connection.getresponse()
                raw = response.read()
                no_body = request["method"] == "HEAD" or response.status in {204, 304}
                content = None if no_body else strict_json(raw)
                expected = item["response"]
                passed = response.status == expected.get("status", 200) and (
                    no_body or json_equal(content, expected.get("json"))
                )
                results.append(
                    {
                        "method": request["method"],
                        "path": path,
                        "expected": expected.get("status", 200),
                        "actual": response.status,
                        "body": redact(content),
                        "passed": passed,
                    }
                )
            finally:
                connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    return {
        "results": results,
        **state,
        "passed": all(row["passed"] for row in results)
        and state["consumed"] == state["total"]
        and state["unexpected"] == 0,
    }
