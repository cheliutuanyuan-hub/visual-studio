"""Pytest configuration: make the ``src`` layout importable."""

import os
import sys

# Ensure the src-layout package is importable without an install.
_SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, os.path.abspath(_SRC))
