"""MERLIN desktop entry point.

Run with:  python app.py

The original `main.py` command-line assistant is untouched and still works on
its own; this wrapper adds the desktop interface around it.
"""
from __future__ import annotations

import os
import sys

# Make `ui` and `services` importable no matter how this file was invoked
# (double-click, `python app.py`, or from another working directory).
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from ui.app import run  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(run())
