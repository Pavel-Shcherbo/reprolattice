"""Portable JSON, JUnit-compatible XML and escaped standalone HTML suite reports."""

import html
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

INVALID_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")
STATUSES = ("passed", "failed", "error", "skipped", "cancelled")


