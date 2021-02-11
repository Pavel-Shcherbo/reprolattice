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


def client_source(output='{"ok": true}', extra=""):
    return (
        "import json,os,urllib.request; "
        'urllib.request.urlopen(os.environ["REPROLATTICE_BASE_URL"]+"/check").read(); '
        + extra
        + f"print({output!r})"
    )


def case(name="control", expected=True, command=None):
    return {
        "id": name,
        "fixture": fixture(expected),
        "tags": ["core"],
        "command": command or [sys.executable, "-c", client_source()],
    }


def suite(cases=None):
    return {"version": 1, "name": "control-suite", "cases": cases or [case()]}
