"""Retry a dependency and persist one inventory receipt in an existing database."""

import argparse
import http.client
import json
import os
import sqlite3
from contextlib import closing
from urllib.parse import urlsplit


