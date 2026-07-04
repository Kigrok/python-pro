#!/usr/bin/env python3
# hooks/common.py — Shared utilities for all hooks.

from __future__ import annotations

from pathlib import Path
from sys import path as _sys_path

# Bootstrap: hook scripts run standalone, so put the plugin root on sys.path.
_ROOT: Path = Path(__file__).resolve().parent.parent
_sys_path.insert(0, str(_ROOT))

from typing import Final  # noqa: E402

from cli.constants import IGNORED_DIRS  # noqa: E402

IGNORED_PARTS: Final[frozenset[str]] = IGNORED_DIRS | frozenset(
    {
        "env",
        "site-packages",
    }
)


def get_target(payload: dict[str, object], require_exists: bool = False) -> Path | None:
    """Extract a Python file path from a hook payload.

    Args:
        payload: The hook payload dict.
        require_exists: If True, only return paths that exist on disk.
    """
    tool_input: object = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw: object = tool_input.get("file_path")
    if not isinstance(raw, str) or not raw.endswith(".py"):
        return None
    path: Path = Path(raw)
    if any(part in IGNORED_PARTS for part in path.parts):
        return None
    if require_exists and not path.exists():
        return None
    return path
