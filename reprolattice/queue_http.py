"""Loopback-only JSON queue fixture; unsupported wire attempts remain visible."""

import hmac
import json
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from .jsonutil import strict_json
from .queue_engine import QueueCapacity, QueueEngine


