"""A real crashed delivery followed by an idempotent or deliberately faulty retry."""

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


