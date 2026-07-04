#!/usr/bin/env python3
# cli/parser.py — Parse output from ruff, flake8, mypy, pylint, pyright, vulture.

from __future__ import annotations

from collections.abc import Callable
from re import MULTILINE, Match, compile
from re import Pattern as _Pattern
from typing import Final

from cli.models import LintError, Severity

Pattern = _Pattern[str]


class LinterParser:
    """Parses output from various linters into LintError objects."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def parse_ruff(output: str, file_path: str) -> list[LintError]:
        """Parse ruff check output."""
        pattern: Pattern = compile(
            r"^(.+?):(\d+):(\d+):\s+(\w+)\s+(.+)$",
            MULTILINE,
        )
        errors: list[LintError] = []
        match: Match[str]
        for match in pattern.finditer(output):
            line_no: int = int(match.group(2))
            col: int = int(match.group(3))
            code: str = match.group(4)
            message: str = match.group(5)
            severity: Severity = Severity.ERROR if code[0] == "E" else Severity.WARNING
            errors.append(
                LintError(
                    file=file_path,
                    line=line_no,
                    col=col,
                    code=code,
                    message=message,
                    linter="ruff",
                    severity=severity,
                )
            )
        return errors

    @staticmethod
    def parse_flake8(output: str, file_path: str) -> list[LintError]:
        """Parse flake8 output."""
        pattern: Pattern = compile(
            r"^(.+?):(\d+):(\d+):\s+(\w+)\s+(.+)$",
            MULTILINE,
        )
        errors: list[LintError] = []
        match: Match[str]
        for match in pattern.finditer(output):
            line_no: int = int(match.group(2))
            col: int = int(match.group(3))
            code: str = match.group(4)
            message: str = match.group(5)
            severity: Severity = (
                Severity.ERROR if code[0] in ("E", "F") else Severity.WARNING
            )
            errors.append(
                LintError(
                    file=file_path,
                    line=line_no,
                    col=col,
                    code=code,
                    message=message,
                    linter="flake8",
                    severity=severity,
                )
            )
        return errors

    @staticmethod
    def parse_mypy(output: str, file_path: str) -> list[LintError]:
        """Parse mypy output."""
        pattern: Pattern = compile(
            r"^(.+?):(\d+):\s+(error|warning|note):\s+(.+)$",
            MULTILINE,
        )
        errors: list[LintError] = []
        match: Match[str]
        for match in pattern.finditer(output):
            line_no: int = int(match.group(2))
            severity_str: str = match.group(3)
            message: str = match.group(4)
            severity: Severity = (
                Severity.ERROR
                if severity_str == "error"
                else Severity.INFO if severity_str == "note" else Severity.WARNING
            )
            errors.append(
                LintError(
                    file=file_path,
                    line=line_no,
                    col=0,
                    code="mypy",
                    message=message,
                    linter="mypy",
                    severity=severity,
                )
            )
        return errors

    @staticmethod
    def parse_pylint(output: str, file_path: str) -> list[LintError]:
        """Parse pylint output."""
        pattern: Pattern = compile(
            r"^(.+?):(\d+):(\d+):\s+([CRWEF]\d+):\s+(.+)$",
            MULTILINE,
        )
        errors: list[LintError] = []
        severity_map: dict[str, Severity] = {
            "C": Severity.INFO,
            "R": Severity.INFO,
            "W": Severity.WARNING,
            "E": Severity.ERROR,
            "F": Severity.ERROR,
        }
        match: Match[str]
        for match in pattern.finditer(output):
            line_no: int = int(match.group(2))
            col: int = int(match.group(3))
            code: str = match.group(4)
            message: str = match.group(5)
            severity: Severity = severity_map.get(
                code[0],
                Severity.WARNING,
            )
            errors.append(
                LintError(
                    file=file_path,
                    line=line_no,
                    col=col,
                    code=code,
                    message=message,
                    linter="pylint",
                    severity=severity,
                )
            )
        return errors

    @staticmethod
    def parse_pyright(output: str, file_path: str) -> list[LintError]:
        """Parse pyright output."""
        pattern: Pattern = compile(
            r"^(.+?):(\d+):(\d+)\s+-\s+" r"(error|warning|information):\s+(.+)$",
            MULTILINE,
        )
        errors: list[LintError] = []
        match: Match[str]
        for match in pattern.finditer(output):
            line_no: int = int(match.group(2))
            col: int = int(match.group(3))
            severity_str: str = match.group(4)
            message: str = match.group(5)
            severity: Severity = (
                Severity.ERROR if severity_str == "error" else Severity.WARNING
            )
            errors.append(
                LintError(
                    file=file_path,
                    line=line_no,
                    col=col,
                    code="pyright",
                    message=message,
                    linter="pyright",
                    severity=severity,
                )
            )
        return errors

    @staticmethod
    def parse_vulture(output: str, file_path: str) -> list[LintError]:
        """Parse vulture output."""
        pattern: Pattern = compile(
            r"^(.+?):(\d+):\s+(.+?)" r"(?:\s+\(\d+%\s+confidence\))?$",
            MULTILINE,
        )
        errors: list[LintError] = []
        match: Match[str]
        for match in pattern.finditer(output):
            line_no: int = int(match.group(2))
            message: str = match.group(3)
            errors.append(
                LintError(
                    file=file_path,
                    line=line_no,
                    col=0,
                    code="vulture",
                    message=message,
                    linter="vulture",
                    severity=Severity.WARNING,
                )
            )
        return errors

    @staticmethod
    def parse_black(output: str, file_path: str) -> list[LintError]:
        """Parse black output."""
        if "would reformat" in output or "reformatted" in output:
            return [
                LintError(
                    file=file_path,
                    line=0,
                    col=0,
                    code="black",
                    message="needs reformatting",
                    linter="black",
                    severity=Severity.WARNING,
                )
            ]
        return []

    @staticmethod
    def parse_isort(output: str, file_path: str) -> list[LintError]:
        """Parse isort output (the --check-only ERROR line)."""
        if "incorrectly sorted" in output or "needs isort" in output:
            return [
                LintError(
                    file=file_path,
                    line=0,
                    col=0,
                    code="isort",
                    message="imports need sorting",
                    linter="isort",
                    severity=Severity.WARNING,
                )
            ]
        return []


PARSERS: Final[dict[str, Callable[..., list[LintError]]]] = {
    "ruff": LinterParser.parse_ruff,
    "flake8": LinterParser.parse_flake8,
    "mypy": LinterParser.parse_mypy,
    "pylint": LinterParser.parse_pylint,
    "pyright": LinterParser.parse_pyright,
    "vulture": LinterParser.parse_vulture,
    "black": LinterParser.parse_black,
    "isort": LinterParser.parse_isort,
}


def parse_output(
    linter: str,
    output: str,
    file_path: str,
) -> list[LintError]:
    """Parse linter output into LintError list."""
    parser: Callable[..., list[LintError]] | None = PARSERS.get(
        linter,
    )
    if parser is None:
        return []
    return parser(output, file_path)
