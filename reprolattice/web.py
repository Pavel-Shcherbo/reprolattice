import http.client
import json
import sys
import threading
from pathlib import Path

from .httpapp import serve
from .harness import check_client
from .replay import make_server

ROOT = Path(__file__).resolve().parents[1]


