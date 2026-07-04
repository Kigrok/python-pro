#!/usr/bin/env python3
# cli/outline.py — Compact, token-frugal code maps from the AST (signatures only).

from __future__ import annotations

from pathlib import Path

from cli.constants import IGNORED_DIRS as _SKIP_DIRS
from cli.type_analyzer import FileAnalysis, TypeAnalyzer


class Outline:
    """Renders signature-only outlines so structure is readable without full files."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def _params(args: list[tuple[str, str]]) -> str:
        """Render a parameter list, dropping self and cls."""
        parts: list[str] = []
        pair: tuple[str, str]
        for pair in args:
            if pair[0] in ("self", "cls"):
                continue
            parts.append(f"{pair[0]}: {pair[1]}")
        return ", ".join(parts)

    @classmethod
    def _render(cls, analysis: FileAnalysis) -> str:
        """Render one file's outline as a compact block."""
        lines: list[str] = [str(analysis.file)]
        klass: object
        for klass in analysis.classes:
            lines.append(f"  class {klass.name}  (L{klass.line})")
            method: object
            for method in klass.methods:
                lines.append(
                    f"    {method.name}({cls._params(method.args)})"
                    f" -> {method.return_type}",
                )
        func: object
        for func in analysis.functions:
            lines.append(
                f"  def {func.name}({cls._params(func.args)}) -> {func.return_type}",
            )
        if not analysis.classes and not analysis.functions:
            lines.append("  (no top-level functions or classes)")
        return "\n".join(lines)

    @classmethod
    def of_file(cls, file_path: str) -> str:
        """Return a compact signature outline for a single file."""
        analysis: FileAnalysis = TypeAnalyzer.analyze(Path(file_path))
        return cls._render(analysis)

    @classmethod
    def of_dir(cls, dir_path: str) -> str:
        """Return outlines for every .py file under a directory."""
        root: Path = Path(dir_path)
        files: list[Path] = sorted(
            p
            for p in root.rglob("*.py")
            if not any(part in _SKIP_DIRS for part in p.parts)
        )
        if not files:
            return f"{dir_path}: no Python files found"

        blocks: list[str] = []
        path: Path
        for path in files:
            analysis: FileAnalysis = TypeAnalyzer.analyze(path)
            blocks.append(cls._render(analysis))
        return "\n\n".join(blocks)

    @classmethod
    def of(cls, path: str) -> str:
        """Outline a file or, if a directory, every .py file beneath it."""
        return cls.of_dir(path) if Path(path).is_dir() else cls.of_file(path)
