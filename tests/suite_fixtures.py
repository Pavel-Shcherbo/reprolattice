import sys


def fixture(expected=True):
    return {
        "application": {"expected_json": {"ok": expected}},
        "interactions": [
            {
                "request": {"method": "GET", "path": "/check"},
                "response": {"json": {"ok": True}},
            }
        ],
    }


