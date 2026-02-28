"""Pytest configuration — ensure omniforge/ is importable from tests/."""

import os
import sys

# Add the repo root to sys.path so ``from omniforge.runner...`` imports work.
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

# Add the runner directory so forge.py can import its own adapters directly.
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "omniforge", "runner"),
)
