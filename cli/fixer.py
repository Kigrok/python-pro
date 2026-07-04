#!/usr/bin/env python3
# cli/fixer.py — Deterministic auto-fix pipeline (codemods + ruff + black).

from __future__ import annotations

from asyncio import (
    create_subprocess_exec,
    wait_for,
)
from asyncio import (
    subprocess as async_subprocess,
)
from dataclasses import dataclass, field
from os import environ
from pathlib import Path
from typing import ClassVar, Final

from cli.codemods import Codemods

# Broad, auto-fixable rule families layered ON TOP of the project's own ruff
# selection (extend-select adds, never replaces). These cover the bulk of the
# python-pro standard deterministically so the AI never touches it:
#   E/F pycodestyle+pyflakes · I import order · UP modern syntax (X | None,
#   list[]) · SIM simplify · C4 comprehensions · B bugbear · RUF · PERF · PIE ·
#   FURB refurb · RET returns · PTH pathlib · TID tidy-imports.
_FIX_PROFILE: Final[str] = "E,F,I,UP,SIM,C4,B,RUF,PERF,PIE,FURB,RET,PTH,TID"


@dataclass(slots=True)
class FixOutcome:
    """What the deterministic pipeline changed on a single file."""

    changed: bool = False
    codemods: list[str] = field(default_factory=list)
    stages: dict[str, bool] = field(default_factory=dict)


class CodeFixer:
    """Run every deterministic fix on a file: codemods, ruff, black."""

    __slots__: tuple[str, ...] = ()

    _BLACK: ClassVar[tuple[str, ...]] = ("black", "--quiet")

    @staticmethod
    def _unsafe_enabled() -> bool:
        """Whether ruff --unsafe-fixes is on (env PYTHON_PRO_UNSAFE_FIXES=0 off)."""
        return environ.get("PYTHON_PRO_UNSAFE_FIXES", "1") != "0"

    @staticmethod
    def _ruff_cmd() -> list[str]:
        """Build the ruff --fix command with the broad extend-select profile."""
        cmd: list[str] = [
            "ruff",
            "check",
            "--fix",
            f"--extend-select={_FIX_PROFILE}",
            "--quiet",
        ]
        if CodeFixer._unsafe_enabled():
            cmd.insert(3, "--unsafe-fixes")
        return cmd

    @staticmethod
    async def _run(cmd: list[str], file_path: str) -> bool:
        """Run one fixer subprocess; True when it ran (a non-zero exit from a
        --fix pass means 'issues remain', not that the tool failed)."""
        try:
            proc = await create_subprocess_exec(
                *cmd,
                file_path,
                stdout=async_subprocess.PIPE,
                stderr=async_subprocess.PIPE,
            )
            await wait_for(proc.communicate(), timeout=30)
            return True
        except (FileNotFoundError, TimeoutError):
            return False

    @staticmethod
    async def auto_fix(file_path: str) -> FixOutcome:
        """Codemods → ruff --fix (broad) → black. Report what changed."""
        path: Path = Path(file_path)
        try:
            before: str = path.read_text()
        except (OSError, UnicodeDecodeError):
            return FixOutcome()

        outcome: FixOutcome = FixOutcome()
        outcome.codemods = Codemods.apply(path)
        outcome.stages["ruff"] = await CodeFixer._run(
            CodeFixer._ruff_cmd(),
            file_path,
        )
        outcome.stages["black"] = await CodeFixer._run(
            list(CodeFixer._BLACK),
            file_path,
        )
        # Second codemod pass cleans up imports ruff may have introduced
        # (e.g. SIM105 adds `import contextlib`) so no self-inflicted residue.
        post: list[str] = Codemods.apply(path)
        outcome.codemods = list(dict.fromkeys(outcome.codemods + post))

        try:
            after: str = path.read_text()
        except (OSError, UnicodeDecodeError):
            after = before
        outcome.changed = after != before
        return outcome
