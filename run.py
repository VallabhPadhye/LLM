#!/usr/bin/env python3
"""
Anviksha launcher.

    python run.py            # start the web app on http://localhost:8000

Teach it by dropping .md/.txt files into data/knowledge/ (before or while it
runs) or by sending "learn: <text>" in chat.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from anviksha.server import main  # noqa: E402

if __name__ == "__main__":
    main()
