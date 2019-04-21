"""A loopback-only, ordered HTTP fixture server without upstream forwarding."""

import copy
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SECRET_KEYS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "password",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "x-api-key",
    "secret",
}


def redact(value):
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if key.casefold().replace("-", "_")
                in {x.replace("-", "_") for x in SECRET_KEYS}
                else redact(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def validate(fixture):
    if not isinstance(fixture, dict):
        raise ValueError("fixture must be an object")
    interactions = fixture.get("interactions")
    if not isinstance(interactions, list) or not interactions:
        raise ValueError("interactions must be a non-empty list")
    for item in interactions:
        if not isinstance(item, dict):
            raise ValueError("each interaction must be an object")
        request, response = item.get("request", {}), item.get("response", {})
        if not isinstance(request, dict) or not isinstance(response, dict):
            raise ValueError("request and response must be objects")
        if request.get("method") not in {
            "GET",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
            "HEAD",
            "OPTIONS",
        }:
            raise ValueError("unsupported request method")
        if not isinstance(request.get("path"), str) or not request["path"].startswith(
            "/"
        ):
            raise ValueError("request path must start with /")
        status = response.get("status", 200)
        if type(status) is not int or not 200 <= status <= 599:
            raise ValueError("response status must be between 200 and 599")
        if status in {204, 304} and response.get("json") is not None:
            raise ValueError("204 and 304 responses cannot contain JSON bodies")
        if not isinstance(response.get("headers", {}), dict):
            raise ValueError("response headers must be an object")
        for key, value in response.get("headers", {}).items():
            if (
                not isinstance(key, str)
                or not isinstance(value, str)
                or any(c in key + value for c in "\r\n")
            ):
                raise ValueError("invalid response header")
            if key.lower() in {"content-length", "transfer-encoding", "connection"}:
                raise ValueError("transport response headers are managed by the server")
        try:
            json.dumps(item, allow_nan=False)
        except (ValueError, TypeError) as error:
            raise ValueError("interaction must contain finite JSON values") from error
    return copy.deepcopy(interactions)


