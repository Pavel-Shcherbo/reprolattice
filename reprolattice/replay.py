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


