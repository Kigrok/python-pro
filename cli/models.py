#!/usr/bin/env python3
# cli/models.py — Data models for lint results and reports.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

__all__ = ["FileReport", "LintError", "LinterResult", "Severity"]


class Severity(StrEnum):
    """Lint error severity levels."""

    ERROR: str = "error"
    WARNING: str = "warning"
    INFO: str = "info"


@dataclass(slots=True)
class LintError:
    """Single lint error from any linter."""

    file: str
    line: int
    col: int
    code: str
    message: str
    linter: str
    severity: Severity = Severity.ERROR

    @property
    def compact(self) -> str:
        """Compact one-line format for terminal output."""
        return (
            f"{self.file}:{self.line}:{self.col}: "
            f"{self.code} {self.message} [{self.linter}]"
        )


@dataclass(slots=True)
class LinterResult:
    """Result from running a single linter on a file."""

    linter: str
    success: bool
    errors: list[LintError] = field(default_factory=list)
    raw_output: str = ""

    @property
    def error_count(self) -> int:
        """Number of errors found."""
        return len(self.errors)


@dataclass(slots=True)
class FileReport:
    """Aggregated lint report for a single file."""

    file: str
    results: list[LinterResult] = field(default_factory=list)

    @property
    def total_errors(self) -> int:
        """Total errors across all linters."""
        return sum(r.error_count for r in self.results)

    @property
    def has_errors(self) -> bool:
        """Whether any linter found errors."""
        return self.total_errors > 0

    def all_errors(self) -> list[LintError]:
        """All errors sorted by line and column."""
        errors: list[LintError] = []
        result: LinterResult
        for result in self.results:
            errors.extend(result.errors)
        return sorted(errors, key=lambda e: (e.line, e.col))
