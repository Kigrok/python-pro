#!/usr/bin/env python3
# cli/validator.py — Validate Python files against python-pro rules.

from __future__ import annotations

from ast import (
    AST,
    AnnAssign,
    Assert,
    Assign,
    AsyncFunctionDef,
    Attribute,
    Call,
    ClassDef,
    Compare,
    Constant,
    Dict,
    Eq,
    ExceptHandler,
    Expr,
    FunctionDef,
    If,
    Import,
    ImportFrom,
    List,
    Module,
    Name,
    NotEq,
    Raise,
    Set,
    arg,
    arguments,
    dump,
    expr,
    get_docstring,
    iter_child_nodes,
    parse,
    stmt,
    walk,
)
from dataclasses import dataclass, field
from pathlib import Path
from sys import argv, exit
from typing import ClassVar

__all__ = ["PythonProValidator", "ValidationIssue", "ValidationReport"]


@dataclass(slots=True)
class ValidationIssue:
    """Single validation issue."""

    file: str
    line: int
    rule: str
    message: str
    severity: str = "error"


@dataclass(slots=True)
class ValidationReport:
    """Validation report for a file."""

    file: str
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        """Count of errors."""
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        """Count of warnings."""
        return sum(1 for i in self.issues if i.severity == "warning")


class PythonProValidator:
    """Validate Python files against python-pro rules."""

    __slots__: tuple[str, ...] = ()

    BANNED_TYPES: ClassVar[frozenset[str]] = frozenset({"Any", "Optional"})
    MAX_FUNCTION_STATEMENTS: ClassVar[int] = 60
    MIN_DUPLICATE_STATEMENTS: ClassVar[int] = 3

    @staticmethod
    def validate(file_path: Path, tree: Module | None = None) -> ValidationReport:
        """Validate a single file. Accepts optional pre-parsed AST tree."""
        report: ValidationReport = ValidationReport(file=str(file_path))

        try:
            content: str = file_path.read_text()
            lines: list[str] = content.split("\n")
            if tree is None:
                tree = parse(content)
        except (SyntaxError, UnicodeDecodeError) as exc:
            report.issues.append(
                ValidationIssue(
                    file=str(file_path),
                    line=0,
                    rule="syntax",
                    message=str(exc),
                    severity="error",
                )
            )
            return report

        PythonProValidator._check_shebang(lines, report)
        PythonProValidator._check_path_comment(lines, report)
        PythonProValidator._check_docstrings(tree, report)
        PythonProValidator._check_slots(tree, report)
        PythonProValidator._check_annotations(tree, report)
        PythonProValidator._check_imports(tree, report)
        PythonProValidator._check_match_case(tree, report)
        PythonProValidator._check_banned_types(tree, report)
        PythonProValidator._check_comparisons(tree, report)
        PythonProValidator._check_mutable_defaults(tree, report)
        PythonProValidator._check_bare_except(tree, report)
        PythonProValidator._check_wildcard_imports(tree, report)
        PythonProValidator._check_function_length(tree, report)
        PythonProValidator._check_duplicate_functions(tree, report)
        PythonProValidator._check_broad_except(tree, report)
        PythonProValidator._check_assert(tree, file_path, report)
        PythonProValidator._check_raise_from(tree, report)
        PythonProValidator._check_inline_imports(tree, report)
        PythonProValidator._check_print_usage(tree, report)
        PythonProValidator._check_classvar(tree, report)

        return report

    @staticmethod
    def _check_shebang(lines: list[str], report: ValidationReport) -> None:
        """Check for shebang line."""
        if not lines or not lines[0].startswith("#!"):
            report.issues.append(
                ValidationIssue(
                    file=report.file,
                    line=1,
                    rule="shebang",
                    message="Missing shebang line",
                    severity="error",
                )
            )

    @staticmethod
    def _check_path_comment(lines: list[str], report: ValidationReport) -> None:
        """Check for path comment."""
        if len(lines) > 1 and not lines[1].startswith("#"):
            report.issues.append(
                ValidationIssue(
                    file=report.file,
                    line=2,
                    rule="path_comment",
                    message="Missing path comment",
                    severity="warning",
                )
            )

    @staticmethod
    def _check_docstrings(tree: Module, report: ValidationReport) -> None:
        """Flag missing one-line docstrings on PUBLIC classes/functions only."""
        for node in walk(tree):
            if not isinstance(
                node,
                (ClassDef, FunctionDef, AsyncFunctionDef),
            ):
                continue
            if node.name.startswith("_") or get_docstring(node):
                continue
            is_class: bool = isinstance(node, ClassDef)
            kind: str = "class" if is_class else "function"
            label: str = node.name if is_class else f"{node.name}()"
            report.issues.append(
                ValidationIssue(
                    file=report.file,
                    line=node.lineno,
                    rule="docstring",
                    message=f"Public {kind} {label} missing docstring",
                    severity="warning",
                )
            )

    @staticmethod
    def _decorator_name(node: expr) -> str:
        """Decorator's bound name: handles @dec, @dec(...), and @mod.dec."""
        if isinstance(node, Name):
            return node.id
        if isinstance(node, Call):
            return PythonProValidator._decorator_name(node.func)
        if isinstance(node, Attribute):
            return node.attr
        return ""

    @staticmethod
    def _check_slots(tree: Module, report: ValidationReport) -> None:
        """Check for __slots__ on classes."""
        for node in walk(tree):
            if isinstance(node, ClassDef):
                # Skip dataclasses, pydantic models, SQLAlchemy models, enums
                decorators: list[str] = [
                    PythonProValidator._decorator_name(d) for d in node.decorator_list
                ]
                if "dataclass" in decorators or "BaseModel" in decorators:
                    continue
                if any(
                    "Base" in (base.id if isinstance(base, Name) else "")
                    for base in node.bases
                ):
                    continue
                if any(
                    "Enum" in (base.id if isinstance(base, Name) else "")
                    for base in node.bases
                ):
                    continue

                has_slots: bool = False
                for n in node.body:
                    if isinstance(n, Assign) and any(
                        isinstance(t, Name) and t.id == "__slots__" for t in n.targets
                    ):
                        has_slots = True
                        break
                    if (
                        isinstance(n, AnnAssign)
                        and isinstance(n.target, Name)
                        and n.target.id == "__slots__"
                    ):
                        has_slots = True
                        break

                if not has_slots:
                    report.issues.append(
                        ValidationIssue(
                            file=report.file,
                            line=node.lineno,
                            rule="slots",
                            message=f"Class {node.name} missing __slots__",
                            severity="warning",
                        )
                    )

    @staticmethod
    def _check_annotations(tree: Module, report: ValidationReport) -> None:
        """Flag missing return types and unannotated class attributes."""
        for node in walk(tree):
            if isinstance(node, (FunctionDef, AsyncFunctionDef)):
                if node.returns is None:
                    report.issues.append(
                        ValidationIssue(
                            file=report.file,
                            line=node.lineno,
                            rule="annotation",
                            message=f"Function {node.name}() missing return type",
                            severity="warning",
                        )
                    )
            elif isinstance(node, ClassDef):
                PythonProValidator._check_class_attrs(node, report)

    @staticmethod
    def _check_class_attrs(
        node: ClassDef,
        report: ValidationReport,
    ) -> None:
        """Flag class attributes assigned without a type annotation."""
        for item in node.body:
            if not isinstance(item, Assign):
                continue
            for target in item.targets:
                if not isinstance(target, Name):
                    continue
                name: str = target.id
                if name == "__slots__" or (
                    name.startswith("__") and name.endswith("__")
                ):
                    continue
                report.issues.append(
                    ValidationIssue(
                        file=report.file,
                        line=item.lineno,
                        rule="annotation",
                        message=f"Class attribute '{name}' missing annotation",
                        severity="warning",
                    )
                )

    @staticmethod
    def _check_imports(tree: Module, report: ValidationReport) -> None:
        """Check for import style."""
        for node in walk(tree):
            if isinstance(node, Import):
                for alias in node.names:
                    if "." not in alias.name and alias.asname is None:
                        report.issues.append(
                            ValidationIssue(
                                file=report.file,
                                line=node.lineno,
                                rule="import",
                                message=(
                                    f"Use 'from {alias.name} import ...' "
                                    f"not 'import {alias.name}'"
                                ),
                                severity="warning",
                            )
                        )

    @staticmethod
    def _check_match_case(tree: Module, report: ValidationReport) -> None:
        """Flag value-dispatch if/elif chains of 3+ branches (use match/case)."""
        elif_continuations: set[int] = set()
        for node in walk(tree):
            if (
                isinstance(node, If)
                and len(node.orelse) == 1
                and isinstance(node.orelse[0], If)
            ):
                elif_continuations.add(id(node.orelse[0]))
        for node in walk(tree):
            if not isinstance(node, If) or id(node) in elif_continuations:
                continue
            branches: int = 1
            cursor: If = node
            while len(cursor.orelse) == 1 and isinstance(cursor.orelse[0], If):
                branches += 1
                cursor = cursor.orelse[0]
            if branches >= 3:
                report.issues.append(
                    ValidationIssue(
                        file=report.file,
                        line=node.lineno,
                        rule="match_case",
                        message=(
                            f"if/elif chain of {branches} branches; use match/case"
                        ),
                        severity="warning",
                    )
                )

    @staticmethod
    def _check_banned_types(tree: Module, report: ValidationReport) -> None:
        """Flag Any / Optional in annotations and typing imports."""
        for node in walk(tree):
            if isinstance(node, ImportFrom) and node.module == "typing":
                for alias in node.names:
                    if alias.name in PythonProValidator.BANNED_TYPES:
                        report.issues.append(
                            ValidationIssue(
                                file=report.file,
                                line=node.lineno,
                                rule="banned_type",
                                message=(
                                    f"Banned import typing.{alias.name}; use a precise "
                                    f"type, 'object', or 'X | None'"
                                ),
                                severity="error",
                            )
                        )
            for ann in PythonProValidator._annotations_of(node):
                if PythonProValidator._names_in(ann) & PythonProValidator.BANNED_TYPES:
                    report.issues.append(
                        ValidationIssue(
                            file=report.file,
                            line=ann.lineno,
                            rule="banned_type",
                            message=(
                                "Any/Optional banned; use a precise type "
                                "or 'X | None'"
                            ),
                            severity="error",
                        )
                    )

    @staticmethod
    def _annotations_of(node: AST) -> list[expr]:
        """Collect annotation expressions attached to a node."""
        anns: list[expr] = []
        if isinstance(node, (FunctionDef, AsyncFunctionDef)):
            if node.returns is not None:
                anns.append(node.returns)
            args: arguments = node.args
            arg: arg
            for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs):
                if arg.annotation is not None:
                    anns.append(arg.annotation)
            for extra in (args.vararg, args.kwarg):
                if extra is not None and extra.annotation is not None:
                    anns.append(extra.annotation)
        elif isinstance(node, AnnAssign) and node.annotation is not None:
            anns.append(node.annotation)
        return anns

    @staticmethod
    def _names_in(node: expr) -> set[str]:
        """Return every Name id and Attribute attr used inside an expression."""
        found: set[str] = set()
        sub: AST
        for sub in walk(node):
            if isinstance(sub, Name):
                found.add(sub.id)
            elif isinstance(sub, Attribute):
                found.add(sub.attr)
        return found

    @staticmethod
    def _check_comparisons(tree: Module, report: ValidationReport) -> None:
        """Flag '== None'/'!= None' and '== True/False' comparisons."""
        for node in walk(tree):
            if not isinstance(node, Compare):
                continue
            if not any(isinstance(op, (Eq, NotEq)) for op in node.ops):
                continue
            operands: list[expr] = [node.left, *node.comparators]
            operand: expr
            for operand in operands:
                if not isinstance(operand, Constant):
                    continue
                if operand.value is None:
                    report.issues.append(
                        ValidationIssue(
                            file=report.file,
                            line=node.lineno,
                            rule="none_comparison",
                            message="Compare to None with 'is'/'is not', not '=='/'!='",
                            severity="error",
                        )
                    )
                    break
                if operand.value is True or operand.value is False:
                    report.issues.append(
                        ValidationIssue(
                            file=report.file,
                            line=node.lineno,
                            rule="bool_comparison",
                            message=(
                                "Test the value directly; drop " "'== True'/'== False'"
                            ),
                            severity="warning",
                        )
                    )
                    break

    @staticmethod
    def _check_mutable_defaults(
        tree: Module,
        report: ValidationReport,
    ) -> None:
        """Flag mutable default arguments (list/dict/set literal or call)."""
        for node in walk(tree):
            if not isinstance(node, (FunctionDef, AsyncFunctionDef)):
                continue
            default: expr | None
            for default in (*node.args.defaults, *node.args.kw_defaults):
                if default is None:
                    continue
                is_literal: bool = isinstance(
                    default,
                    (List, Dict, Set),
                )
                is_factory: bool = (
                    isinstance(default, Call)
                    and isinstance(default.func, Name)
                    and default.func.id in {"list", "dict", "set"}
                )
                if is_literal or is_factory:
                    report.issues.append(
                        ValidationIssue(
                            file=report.file,
                            line=node.lineno,
                            rule="mutable_default",
                            message=(
                                f"Mutable default in {node.name}(); use None and "
                                f"initialise in the body"
                            ),
                            severity="error",
                        )
                    )

    @staticmethod
    def _check_bare_except(tree: Module, report: ValidationReport) -> None:
        """Flag bare 'except:' clauses."""
        for node in walk(tree):
            if isinstance(node, ExceptHandler) and node.type is None:
                report.issues.append(
                    ValidationIssue(
                        file=report.file,
                        line=node.lineno,
                        rule="bare_except",
                        message="Bare 'except:'; catch a specific exception type",
                        severity="error",
                    )
                )

    @staticmethod
    def _check_wildcard_imports(
        tree: Module,
        report: ValidationReport,
    ) -> None:
        """Flag wildcard 'from x import *' imports."""
        for node in walk(tree):
            if not isinstance(node, ImportFrom):
                continue
            if any(alias.name == "*" for alias in node.names):
                report.issues.append(
                    ValidationIssue(
                        file=report.file,
                        line=node.lineno,
                        rule="wildcard_import",
                        message="Wildcard import; bind exact names instead",
                        severity="warning",
                    )
                )

    @staticmethod
    def _own_statement_count(node: AST) -> int:
        """Count statements node owns, NOT those inside nested def/class bodies.

        Recurses through compound statements and match/case arms, but treats a
        nested function or class as a single statement (its body is its own).
        """
        total: int = 0
        child: AST
        for child in iter_child_nodes(node):
            if isinstance(
                child,
                (FunctionDef, AsyncFunctionDef, ClassDef),
            ):
                total += 1
                continue
            if isinstance(child, stmt):
                total += 1
            total += PythonProValidator._own_statement_count(child)
        return total

    @staticmethod
    def _check_function_length(
        tree: Module,
        report: ValidationReport,
    ) -> None:
        """Flag functions too long to be a single logical action."""
        for node in walk(tree):
            if not isinstance(node, (FunctionDef, AsyncFunctionDef)):
                continue
            statements: int = PythonProValidator._own_statement_count(node)
            if statements > PythonProValidator.MAX_FUNCTION_STATEMENTS:
                report.issues.append(
                    ValidationIssue(
                        file=report.file,
                        line=node.lineno,
                        rule="function_length",
                        message=(
                            f"{node.name}() has {statements} statements; split it "
                            f"into single-purpose helpers"
                        ),
                        severity="warning",
                    )
                )

    @staticmethod
    def _check_duplicate_functions(
        tree: Module,
        report: ValidationReport,
    ) -> None:
        """Flag duplicate function bodies, comparing only within one scope (DRY)."""
        PythonProValidator._dup_in_scope(tree.body, report)
        for node in walk(tree):
            if isinstance(node, ClassDef):
                PythonProValidator._dup_in_scope(node.body, report)

    @staticmethod
    def _dup_in_scope(
        body: list[stmt],
        report: ValidationReport,
    ) -> None:
        """Flag functions in a single scope whose bodies are byte-identical."""
        seen: dict[str, str] = {}
        node: stmt
        for node in body:
            if not isinstance(node, (FunctionDef, AsyncFunctionDef)):
                continue
            stmts: list[stmt] = [
                stmt
                for stmt in node.body
                if not (isinstance(stmt, Expr) and isinstance(stmt.value, Constant))
            ]
            if len(stmts) < PythonProValidator.MIN_DUPLICATE_STATEMENTS:
                continue
            key: str = "".join(dump(stmt, annotate_fields=False) for stmt in stmts)
            first: str | None = seen.get(key)
            if first is None:
                seen[key] = node.name
                continue
            report.issues.append(
                ValidationIssue(
                    file=report.file,
                    line=node.lineno,
                    rule="duplicate_code",
                    message=(
                        f"{node.name}() body duplicates {first}(); unify into a "
                        f"shared helper"
                    ),
                    severity="warning",
                )
            )

    @staticmethod
    def _check_broad_except(tree: Module, report: ValidationReport) -> None:
        """Flag overbroad except Exception / except BaseException (warning)."""
        for node in walk(tree):
            if not isinstance(node, ExceptHandler):
                continue
            if isinstance(node.type, Name) and node.type.id in {
                "Exception",
                "BaseException",
            }:
                report.issues.append(
                    ValidationIssue(
                        file=report.file,
                        line=node.lineno,
                        rule="broad_except",
                        message=(
                            f"'except {node.type.id}' is overbroad; catch a "
                            f"specific type (ok only when logging and re-raising)"
                        ),
                        severity="warning",
                    )
                )

    @staticmethod
    def _check_assert(
        tree: Module,
        file_path: Path,
        report: ValidationReport,
    ) -> None:
        """Flag assert outside test files — python -O strips it."""
        name: str = file_path.name
        if (
            name.startswith("test_")
            or name.endswith("_test.py")
            or "tests" in file_path.parts
        ):
            return
        for node in walk(tree):
            if isinstance(node, Assert):
                report.issues.append(
                    ValidationIssue(
                        file=report.file,
                        line=node.lineno,
                        rule="assert",
                        message=(
                            "assert is stripped by -O; raise ValueError/TypeError"
                        ),
                        severity="warning",
                    )
                )

    @staticmethod
    def _collect_raises(node: AST, out: list[Raise]) -> None:
        """Collect Raise nodes in node, not descending into nested def/class."""
        if isinstance(node, Raise):
            out.append(node)
        child: AST
        for child in iter_child_nodes(node):
            if isinstance(child, (FunctionDef, AsyncFunctionDef, ClassDef)):
                continue
            PythonProValidator._collect_raises(child, out)

    @staticmethod
    def _check_raise_from(tree: Module, report: ValidationReport) -> None:
        """Flag 'raise X' inside except without 'from exc' (B904, warning)."""
        for handler in walk(tree):
            if not isinstance(handler, ExceptHandler):
                continue
            raises: list[Raise] = []
            stmt_node: stmt
            for stmt_node in handler.body:
                PythonProValidator._collect_raises(stmt_node, raises)
            raised: Raise
            for raised in raises:
                if raised.exc is not None and raised.cause is None:
                    report.issues.append(
                        ValidationIssue(
                            file=report.file,
                            line=raised.lineno,
                            rule="raise_from",
                            message=(
                                "raise inside except without 'from exc'; "
                                "preserve the traceback chain"
                            ),
                            severity="warning",
                        )
                    )

    @staticmethod
    def _check_inline_imports(tree: Module, report: ValidationReport) -> None:
        """Flag imports inside functions/methods (should be at top level)."""
        for node in walk(tree):
            if not isinstance(node, (FunctionDef, AsyncFunctionDef)):
                continue
            for child in walk(node):
                if (
                    isinstance(child, (Import, ImportFrom))
                    and child.lineno > node.lineno
                ):
                    report.issues.append(
                        ValidationIssue(
                            file=report.file,
                            line=child.lineno,
                            rule="inline_import",
                            message=f"Import inside {node.name}() — move to top level",
                            severity="warning",
                        )
                    )

    @staticmethod
    def _check_print_usage(tree: Module, report: ValidationReport) -> None:
        """Flag print() usage in non-test code (prefer logging)."""
        for node in walk(tree):
            if not isinstance(node, Call):
                continue
            if isinstance(node.func, Name) and node.func.id == "print":
                report.issues.append(
                    ValidationIssue(
                        file=report.file,
                        line=node.lineno,
                        rule="print_usage",
                        message="print() — prefer logging module",
                        severity="warning",
                    )
                )

    @staticmethod
    def _check_classvar(tree: Module, report: ValidationReport) -> None:
        """Flag class-level constants missing ClassVar annotation."""
        for node in walk(tree):
            if not isinstance(node, ClassDef):
                continue
            for item in node.body:
                if not isinstance(item, AnnAssign):
                    continue
                if not isinstance(item.target, Name):
                    continue
                name = item.target.id
                if name.startswith("_"):
                    continue
                if item.annotation is None:
                    continue
                # Check if it's a constant (UPPERCASE).
                if name.isupper():
                    ann_str = dump(item.annotation)
                    if "ClassVar" not in ann_str:
                        report.issues.append(
                            ValidationIssue(
                                file=report.file,
                                line=item.lineno,
                                rule="classvar",
                                message=f"Class constant {name} should use ClassVar",
                                severity="warning",
                            )
                        )


def validate_directory(dir_path: Path) -> list[ValidationReport]:
    """Validate all Python files in a directory."""
    reports: list[ValidationReport] = []
    for f in sorted(dir_path.rglob("*.py")):
        if any(p in str(f) for p in ["venv", "__pycache__", ".venv"]):
            continue
        report: ValidationReport = PythonProValidator.validate(f)
        if report.issues:
            reports.append(report)
    return reports


def print_reports(reports: list[ValidationReport]) -> None:
    """Print validation reports."""
    total_errors: int = 0
    total_warnings: int = 0

    for report in reports:
        if report.issues:
            print(f"\n{'=' * 60}")
            print(f"File: {report.file}")
            print(f"{'=' * 60}")
            for issue in report.issues:
                icon: str = "❌" if issue.severity == "error" else "⚠️"
                print(f"  {icon} Line {issue.line}: [{issue.rule}] {issue.message}")
            total_errors += report.error_count
            total_warnings += report.warning_count

    print(f"\n{'=' * 60}")
    print(f"Summary: {total_errors} errors, {total_warnings} warnings")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    if len(argv) < 2:
        print("Usage: python -m cli.validator <directory>")
        exit(1)

    dir_path: Path = Path(argv[1])
    if not dir_path.exists():
        print(f"Directory not found: {dir_path}")
        exit(1)

    reports: list[ValidationReport] = validate_directory(dir_path)
    print_reports(reports)
