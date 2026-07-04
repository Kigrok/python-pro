#!/usr/bin/env python3
# cli/pre_commit.py — Auto-fix BEFORE AI sees the code: the ultimate token saver.

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
_VENV: Final[Path] = _ROOT / ".venv" / "bin"


def _find_tool(name: str) -> str | None:
    """Find a tool in venv or system PATH."""
    venv_path = _VENV / f"{name}"
    if venv_path.is_file():
        return str(venv_path)
    # Check system PATH.
    import shutil

    return shutil.which(name)


@dataclass(slots=True)
class PreCommitResult:
    """Result of pre-commit auto-fix."""

    file: str
    fixed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    original_size: int = 0
    fixed_size: int = 0

    @property
    def has_fixes(self) -> bool:
        return bool(self.fixed)

    @property
    def size_delta(self) -> int:
        return self.fixed_size - self.original_size

    def to_compact(self) -> str:
        if not self.fixed:
            return f"{self.file}: no auto-fixes"
        return (
            f"{self.file}: {len(self.fixed)} auto-fix(es) [{self.size_delta:+d} bytes]"
        )

    def to_diff_summary(self) -> str:
        if not self.fixed:
            return ""
        return "\n".join(f"  {f}" for f in self.fixed)


class PreCommitFixer:
    """Run all auto-fixers BEFORE AI edits the code."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def fix_all(
        file_path: str,
        dry_run: bool = True,
    ) -> PreCommitResult:
        """Run all fixers and return what was fixed."""
        path = Path(file_path)
        if not path.exists():
            return PreCommitResult(file=file_path, errors=["file not found"])

        original = path.read_text(encoding="utf-8", errors="replace")
        result = PreCommitResult(
            file=file_path,
            original_size=len(original.encode()),
        )

        # 1. Autoflake — remove unused imports.
        try:
            from cli.codemods import Codemods

            new_source, changes = Codemods.remove_unused_imports(original)
            if changes:
                result.fixed.extend(changes)
                original = new_source
        except Exception as e:
            result.errors.append(f"autoflake: {e}")

        # 2. Isort — sort imports.
        try:
            from cli.codemods import Codemods

            new_source, changes = Codemods.sort_imports(original)
            if changes:
                result.fixed.extend(changes)
                original = new_source
        except Exception as e:
            result.errors.append(f"isort: {e}")

        # 3. Black — format code.
        if not dry_run:
            try:
                proc = subprocess.run(
                    ["black", "--quiet", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if proc.returncode == 0:
                    result.fixed.append("formatted with black")
                    original = path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                result.errors.append(f"black: {e}")

        # 4. Pyupgrade — modernize syntax.
        try:
            from cli.codemods import Codemods

            new_source, changes = Codemods.modernize_syntax(original)
            if changes:
                result.fixed.extend(changes)
                original = new_source
        except Exception as e:
            result.errors.append(f"pyupgrade: {e}")

        # 5. Ruff fix — auto-fix lint issues.
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ruff",
                    "check",
                    "--fix",
                    "--unsafe-fixes",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode == 0:
                # Check if file changed.
                new_content = path.read_text(encoding="utf-8", errors="replace")
                if new_content != original:
                    result.fixed.append("ruff auto-fix")
                    original = new_content
        except Exception as e:
            result.errors.append(f"ruff: {e}")

        # Write back if not dry run.
        if not dry_run and result.fixed:
            try:
                path.write_text(original, encoding="utf-8")
            except Exception as e:
                result.errors.append(f"write: {e}")

        result.fixed_size = len(original.encode())
        return result

    @staticmethod
    def fix_imports(file_path: str, dry_run: bool = True) -> PreCommitResult:
        """Fix only imports (autoflake + isort)."""
        path = Path(file_path)
        if not path.exists():
            return PreCommitResult(file=file_path, errors=["file not found"])

        original = path.read_text(encoding="utf-8", errors="replace")
        result = PreCommitResult(
            file=file_path,
            original_size=len(original.encode()),
        )

        try:
            from cli.codemods import Codemods

            new_source, changes = Codemods.remove_unused_imports(original)
            if changes:
                result.fixed.extend(changes)
                original = new_source
        except Exception as e:
            result.errors.append(f"autoflake: {e}")

        try:
            from cli.codemods import Codemods

            new_source, changes = Codemods.sort_imports(original)
            if changes:
                result.fixed.extend(changes)
                original = new_source
        except Exception as e:
            result.errors.append(f"isort: {e}")

        if not dry_run and result.fixed:
            try:
                path.write_text(original, encoding="utf-8")
            except Exception as e:
                result.errors.append(f"write: {e}")

        result.fixed_size = len(original.encode())
        return result

    @staticmethod
    def fix_format(file_path: str, dry_run: bool = True) -> PreCommitResult:
        """Fix formatting only (black)."""
        path = Path(file_path)
        if not path.exists():
            return PreCommitResult(file=file_path, errors=["file not found"])

        original = path.read_text(encoding="utf-8", errors="replace")
        result = PreCommitResult(
            file=file_path,
            original_size=len(original.encode()),
        )

        try:
            args = ["black", "--check", "--quiet", str(path)]
            if not dry_run:
                args = ["black", "--quiet", str(path)]

            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode == 0:
                result.fixed.append("formatted with black")
        except Exception as e:
            result.errors.append(f"black: {e}")

        result.fixed_size = len(original.encode())
        return result

    @staticmethod
    def fix_security(file_path: str, dry_run: bool = True) -> PreCommitResult:
        """Fix security issues (bandit auto-fix where possible)."""
        path = Path(file_path)
        if not path.exists():
            return PreCommitResult(file=file_path, errors=["file not found"])

        result = PreCommitResult(file=file_path)

        try:
            proc = subprocess.run(
                ["bandit", "-q", "-f", "json", str(path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.stdout:
                import json

                data = json.loads(proc.stdout)
                findings = data.get("results", [])
                if not findings:
                    result.fixed.append("no security issues")
        except Exception as e:
            result.errors.append(f"bandit: {e}")

        return result

    @staticmethod
    def batch_fix(
        file_paths: list[str],
        dry_run: bool = True,
    ) -> list[PreCommitResult]:
        """Fix multiple files."""
        return [PreCommitFixer.fix_all(fp, dry_run=dry_run) for fp in file_paths]
