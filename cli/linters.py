#!/usr/bin/env python3
# cli/linters.py — Run linters in parallel and collect results.

from __future__ import annotations

from asyncio import (
    Semaphore,
    create_subprocess_exec,
    gather,
    wait_for,
)
from asyncio import (
    subprocess as async_subprocess,
)
from typing import Final

from cli.models import LinterResult
from cli.parser import parse_output

__all__ = ["LINTER_COMMANDS", "run_linters", "run_linters_batch"]

LINTER_COMMANDS: Final[dict[str, list[str]]] = {
    "ruff": ["ruff", "check"],
    "flake8": ["flake8"],
    "mypy": ["mypy"],
    "pylint": ["pylint", "--disable=C0114,C0115,C0116"],
    "pyright": ["pyright"],
    "vulture": ["vulture"],
    "black": ["black", "--check"],
    "isort": ["isort", "--check-only"],
}

LINTERS: Final[list[str]] = list(LINTER_COMMANDS.keys())
_BATCH_SEM: Semaphore = Semaphore(8)


class LinterRunner:
    """Runs linters in parallel and collects results."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    async def _run_single(
        linter: str,
        cmd: list[str],
        file_path: str,
    ) -> LinterResult:
        """Run a single linter on a file."""
        try:
            proc = await create_subprocess_exec(
                *cmd,
                file_path,
                stdout=async_subprocess.PIPE,
                stderr=async_subprocess.PIPE,
            )
            stdout_bytes: bytes
            stderr_bytes: bytes
            stdout_bytes, stderr_bytes = await wait_for(
                proc.communicate(),
                timeout=10,
            )
            stdout: str = stdout_bytes.decode(errors="replace")
            stderr: str = stderr_bytes.decode(errors="replace")
            output: str = stdout or stderr
            errors = parse_output(linter, output, file_path)
            return LinterResult(
                linter=linter,
                success=proc.returncode == 0,
                errors=errors,
            )
        except FileNotFoundError:
            return LinterResult(
                linter=linter,
                success=False,
                raw_output=f"{linter} not installed",
            )
        except TimeoutError:
            return LinterResult(
                linter=linter,
                success=False,
                raw_output=f"{linter} timed out",
            )


async def run_linters(
    file_path: str,
    linters: list[str] | None = None,
) -> list[LinterResult]:
    """Run all linters on a file in parallel."""
    target: list[str] = linters or LINTERS
    tasks = [
        LinterRunner._run_single(name, LINTER_COMMANDS[name], file_path)
        for name in target
        if name in LINTER_COMMANDS
    ]
    return list(await gather(*tasks))


async def run_linters_batch(
    file_paths: list[str],
    linters: list[str] | None = None,
) -> dict[str, list[LinterResult]]:
    """Run linters on multiple files concurrently with bounded parallelism."""

    async def _limited(fp: str) -> tuple[str, list[LinterResult]]:
        async with _BATCH_SEM:
            return fp, await run_linters(fp, linters)

    pairs: list[tuple[str, list[LinterResult]]] = list(
        await gather(*(_limited(fp) for fp in file_paths))
    )
    return dict(pairs)
