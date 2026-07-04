#!/usr/bin/env python3
# cli/runner.py — Run the project's pytest suite for a target and summarise it.

from __future__ import annotations

from asyncio import create_subprocess_exec
from asyncio.subprocess import PIPE, Process
from pathlib import Path
from sys import executable
from typing import Final

_TAIL_LINES: Final[int] = 25
_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
_VENV_PYTHON: Final[Path] = _ROOT / ".venv" / "bin" / "python3"


def _find_python() -> str:
    """Return venv python if available, else system python."""
    if _VENV_PYTHON.is_file():
        return str(_VENV_PYTHON)
    return executable


class TestRunner:
    """Runs pytest on a file or directory and returns a compact summary."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def _workdir(target: Path) -> Path:
        """Pick a sensible working directory for the run."""
        return target if target.is_dir() else target.parent

    @staticmethod
    async def run(target: str, expression: str | None = None) -> str:
        """Run pytest on target (optional -k expression); return summary text."""
        path: Path = Path(target).resolve()
        if not path.exists():
            return f"{target}: path not found"

        python: str = _find_python()
        args: list[str] = ["-m", "pytest", "-q", "--no-header", str(path)]
        if expression:
            args.extend(["-k", expression])

        workdir: str = str(path.parent) if path.is_dir() else str(_ROOT)
        proc: Process = await create_subprocess_exec(
            python,
            *args,
            stdout=PIPE,
            stderr=PIPE,
            cwd=workdir,
        )
        out: bytes
        err: bytes
        out, err = await proc.communicate()

        text: str = (
            out.decode("utf-8", "replace") + err.decode("utf-8", "replace")
        ).strip()
        lines: list[str] = text.splitlines()
        tail: list[str] = lines[-_TAIL_LINES:] if len(lines) > _TAIL_LINES else lines
        status: str = (
            "passed" if proc.returncode == 0 else f"failed (exit {proc.returncode})"
        )
        return f"pytest {target}: {status}\n" + "\n".join(tail)
