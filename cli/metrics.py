#!/usr/bin/env python3
# cli/metrics.py — Lightweight cyclomatic-complexity report (no external deps).

from __future__ import annotations

from ast import (
    Assert,
    AsyncFor,
    AsyncFunctionDef,
    BoolOp,
    ExceptHandler,
    For,
    FunctionDef,
    If,
    IfExp,
    While,
    comprehension,
    match_case,
    parse,
    walk,
)
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_DEFAULT_MAX: Final[int] = 10


@dataclass(slots=True)
class FunctionComplexity:
    """Cyclomatic complexity of a single function."""

    name: str
    line: int
    score: int


class ComplexityAnalyzer:
    """Computes cyclomatic complexity per function from the AST."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def _score(func: FunctionDef | AsyncFunctionDef) -> int:
        """Cyclomatic complexity for one function."""
        score: int = 1
        node: object
        for node in walk(func):
            match node:
                case (
                    If()
                    | For()
                    | AsyncFor()
                    | While()
                    | ExceptHandler()
                    | IfExp()
                    | Assert()
                ):
                    score += 1
                case BoolOp():
                    score += len(node.values) - 1
                case comprehension():
                    score += 1 + len(node.ifs)
                case match_case():
                    score += 1
                case _:
                    pass
        return score

    @classmethod
    def complexities(
        cls,
        file_path: str,
        tree: object = None,
    ) -> list[FunctionComplexity]:
        """Cyclomatic complexity per function, worst first (empty on error)."""
        if tree is None:
            path: Path = Path(file_path)
            try:
                tree = parse(path.read_text(), str(path))
            except (OSError, SyntaxError):
                return []
        results: list[FunctionComplexity] = [
            FunctionComplexity(node.name, node.lineno, cls._score(node))
            for node in walk(tree)
            if isinstance(node, (FunctionDef, AsyncFunctionDef))
        ]
        results.sort(key=lambda r: -r.score)
        return results

    @classmethod
    def over_threshold(
        cls,
        file_path: str,
        max_complexity: int = _DEFAULT_MAX,
        tree: object = None,
    ) -> list[FunctionComplexity]:
        """Functions whose cyclomatic complexity exceeds max_complexity."""
        return [
            fc for fc in cls.complexities(file_path, tree) if fc.score > max_complexity
        ]

    @classmethod
    def report(cls, file_path: str, max_complexity: int = _DEFAULT_MAX) -> str:
        """Report functions exceeding max_complexity and the worst overall."""
        results: list[FunctionComplexity] = cls.complexities(file_path)
        if not results:
            return f"{file_path}: no functions found"

        worst: FunctionComplexity = results[0]
        over: list[FunctionComplexity] = [
            r for r in results if r.score > max_complexity
        ]
        lines: list[str] = [
            f"{file_path}: {len(results)} functions, "
            f"max complexity {worst.score} ({worst.name})",
        ]
        if over:
            lines.append(f"  {len(over)} over threshold {max_complexity}:")
            item: FunctionComplexity
            for item in over:
                lines.append(f"    line {item.line} {item.name}: {item.score}")
        else:
            lines.append(f"  all functions within threshold {max_complexity}")
        return "\n".join(lines)
