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


