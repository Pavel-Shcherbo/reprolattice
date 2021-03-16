import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from suite_fixtures import case, suite

ROOT = Path(__file__).resolve().parents[1]


class SuiteCliTests(unittest.TestCase):
    pass
