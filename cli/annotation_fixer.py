#!/usr/bin/env python3
# cli/annotation_fixer.py — Report variables missing type annotations (no writes).

from __future__ import annotations

from ast import (
    AST,
    Assign,
    ClassDef,
    Constant,
    Dict,
    List,
    Module,
    Name,
    Set,
    Tuple,
    expr,
    parse,
    stmt,
    walk,
)
from dataclasses import dataclass
from pathlib import Path
from sys import argv, exit
from typing import Final

from cli.constants import IGNORED_DIRS as _IGNORED_PARTS

# Literal-only inference; calls/names are reported with no suggestion.
_LITERAL_INFERENCE: Final[dict[type[expr], str]] = {
    List: "list",
    Dict: "dict",
    Set: "set",
    Tuple: "tuple",
}


@dataclass(slots=True)
class MissingAnnotation:
    """A variable assignment that lacks a type annotation."""

    line: int
    name: str
    suggestion: str
    scope: str


class AnnotationReporter:
    """Detect missing type annotations without mutating files."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def check_file(
        file_path: Path,
        tree: Module | None = None,
    ) -> list[MissingAnnotation]:
        """Return missing-annotation issues for a file. Never writes."""
        if tree is None:
            try:
                tree = parse(file_path.read_text())
            except (SyntaxError, UnicodeDecodeError):
                return []

        issues: list[MissingAnnotation] = []
        node: AST
        for node in walk(tree):
            if isinstance(node, ClassDef):
                AnnotationReporter._check_class(node, issues)
        AnnotationReporter._check_module(tree, issues)
        return sorted(issues, key=lambda i: i.line)

    @staticmethod
    def _check_module(
        tree: Module,
        issues: list[MissingAnnotation],
    ) -> None:
        """Flag module-level bare assignments."""
        item: stmt
        for item in tree.body:
            if isinstance(item, Assign):
                AnnotationReporter._flag(item, "module", issues)

    @staticmethod
    def _check_class(
        node: ClassDef,
        issues: list[MissingAnnotation],
    ) -> None:
        """Flag class-level bare assignments (skip __slots__/dunders)."""
        item: stmt
        for item in node.body:
            if isinstance(item, Assign):
                AnnotationReporter._flag(item, f"class {node.name}", issues)

    @staticmethod
    def _flag(
        assign: Assign,
        scope: str,
        issues: list[MissingAnnotation],
    ) -> None:
        """Append an issue per bare Name target on an assignment."""
        target: expr
        for target in assign.targets:
            if not isinstance(target, Name):
                continue
            name: str = target.id
            if name == "__slots__" or (name.startswith("__") and name.endswith("__")):
                continue
            issues.append(
                MissingAnnotation(
                    line=assign.lineno,
                    name=name,
                    suggestion=AnnotationReporter._infer_literal(assign.value),
                    scope=scope,
                )
            )

    @staticmethod
    def _infer_literal(value: expr) -> str:
        """Infer a type only from literals; '' when unknown."""
        if isinstance(value, Constant):
            return type(value.value).__name__ if value.value is not None else "None"
        return _LITERAL_INFERENCE.get(type(value), "")


def check_directory(dir_path: Path) -> dict[str, list[MissingAnnotation]]:
    """Report missing annotations for every Python file in a directory."""
    results: dict[str, list[MissingAnnotation]] = {}
    f: Path
    for f in sorted(dir_path.rglob("*.py")):
        if any(part in _IGNORED_PARTS for part in f.parts):
            continue
        issues: list[MissingAnnotation] = AnnotationReporter.check_file(f)
        if issues:
            results[str(f)] = issues
    return results


def main() -> None:
    """CLI: report missing annotations under a directory."""
    if len(argv) < 2:
        print("Usage: python -m cli.annotation_fixer <directory>")
        exit(1)

    target: Path = Path(argv[1])
    if not target.exists():
        print(f"Path not found: {target}")
        exit(1)

    results: dict[str, list[MissingAnnotation]] = check_directory(target)
    total: int = sum(len(v) for v in results.values())
    fp: str
    issues: list[MissingAnnotation]
    for fp, issues in results.items():
        print(f"\n{fp}: {len(issues)} missing")
        issue: MissingAnnotation
        for issue in issues:
            hint: str = f" → {issue.suggestion}" if issue.suggestion else ""
            print(f"  line {issue.line}: {issue.name} [{issue.scope}]{hint}")
    print(f"\nTotal: {total} variables missing annotations")
    exit(1 if total else 0)


if __name__ == "__main__":
    main()
