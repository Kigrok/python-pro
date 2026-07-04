#!/usr/bin/env python3
# hooks/pre_commit.py — Run python-pro validation before commit.

from __future__ import annotations

import ast
from pathlib import Path
from sys import path as _sys_path

# Bootstrap: git hooks run standalone, so put the plugin root on sys.path.
_sys_path.insert(0, str(Path(__file__).resolve().parent.parent))

from subprocess import run as subprocess_run
from sys import exit

from cli.deps import StdlibFirstChecker
from cli.metrics import ComplexityAnalyzer
from cli.security import SecurityScanner
from cli.validator import PythonProValidator, ValidationReport


def get_staged_files() -> list[str]:
    """Get list of staged Python files."""
    result = subprocess_run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return []
    return [
        f
        for f in result.stdout.strip().split("\n")
        if f.endswith(".py") and Path(f).exists()
    ]


def main() -> None:
    """Run validation on staged files."""
    files: list[str] = get_staged_files()
    if not files:
        print("No Python files staged")
        exit(0)

    total_errors: int = 0
    total_warnings: int = 0

    for f in files:
        # Read and parse once.
        try:
            source = Path(f).read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
        except (SyntaxError, OSError):
            continue

        # AST validation.
        report: ValidationReport = PythonProValidator.validate(Path(f), tree)
        if report.issues:
            print(f"\n{f}:")
            for issue in report.issues:
                icon: str = "❌" if issue.severity == "error" else "⚠️"
                print(f"  {icon} Line {issue.line}: [{issue.rule}] {issue.message}")
            total_errors += report.error_count
            total_warnings += report.warning_count

        # Security scan (reuse parsed tree).
        security = SecurityScanner.findings(f, tree)
        if security:
            if not report.issues:
                print(f"\n{f}:")
            for finding in security:
                print(
                    f"  🔒 Line {finding.line}: [security/{finding.rule}] {finding.message}"
                )
                total_errors += 1

        # Complexity check (reuse parsed tree).
        complexity = ComplexityAnalyzer.over_threshold(f, 10, tree)
        if complexity:
            if not report.issues and not security:
                print(f"\n{f}:")
            for func in complexity:
                print(
                    f"  ⚡ Line {func.line}: [complexity] {func.name}() CC={func.score}"
                )
                total_warnings += 1

        # Dependencies check (reuse parsed tree).
        deps = StdlibFirstChecker.findings(f, tree)
        if deps:
            if not report.issues and not security and not complexity:
                print(f"\n{f}:")
            for dep in deps:
                print(
                    f"  📦 Line {dep.line}: [{dep.rule}] {dep.module} → {dep.suggestion}"
                )
                total_warnings += 1

    if total_errors > 0:
        print(f"\n❌ {total_errors} errors, {total_warnings} warnings")
        print("Commit blocked. Fix errors first.")
        exit(1)
    elif total_warnings > 0:
        print(f"\n⚠️ {total_warnings} warnings (commit allowed)")
        exit(0)
    else:
        print("\n✅ All checks passed")
        exit(0)


if __name__ == "__main__":
    main()
