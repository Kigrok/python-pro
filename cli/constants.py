#!/usr/bin/env python3
# cli/constants.py — Shared constants for python-pro.

from __future__ import annotations

from typing import Final

__all__ = ["IGNORED_DIRS", "PYTHON_EXTENSIONS"]

# Directories to ignore in file scanning.
IGNORED_DIRS: Final[frozenset[str]] = frozenset(
    {
        "venv",
        ".venv",
        "__pycache__",
        "node_modules",
        ".git",
        "dist",
        "build",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".eggs",
        "*.egg-info",
        "env",
    }
)

# File extensions to scan.
PYTHON_EXTENSIONS: Final[frozenset[str]] = frozenset({".py", ".pyi"})
