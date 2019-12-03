"""Finite, bounded JSON values at scenario and process boundaries."""

import json
import math


def validate_json(value, max_bytes=1024 * 1024, max_depth=100, max_nodes=100000):
    pending = [(value, 0)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if depth > max_depth or nodes > max_nodes:
            raise ValueError("JSON structure exceeds the supported budget")
        if current is None or type(current) in (bool, int, str):
            continue
        if type(current) is float:
            if not math.isfinite(current):
                raise ValueError("JSON numbers must be finite")
        elif type(current) is list:
            pending.extend((item, depth + 1) for item in current)
        elif type(current) is dict:
            if any(not isinstance(key, str) for key in current):
                raise ValueError("JSON object keys must be strings")
            pending.extend((item, depth + 1) for item in current.values())
        else:
            raise ValueError("value contains an unsupported JSON type")
    try:
        encoded = json.dumps(value, allow_nan=False).encode()
    except (ValueError, TypeError, RecursionError) as error:
        raise ValueError("value cannot be represented as bounded JSON") from error
    if len(encoded) > max_bytes:
        raise ValueError("JSON value exceeds the byte budget")
    return value


