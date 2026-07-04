#!/usr/bin/env python3
# cli/type_analyzer.py — Analyze Python code and extract type information.

from __future__ import annotations

from ast import (
    AnnAssign,
    Assign,
    AsyncFunctionDef,
    Attribute,
    BinOp,
    Call,
    ClassDef,
    Constant,
    Dict,
    FunctionDef,
    Import,
    ImportFrom,
    List,
    Module,
    Name,
    Set,
    Subscript,
    Tuple,
    dump,
    expr,
    get_docstring,
    iter_child_nodes,
    parse,
)
from dataclasses import dataclass, field
from pathlib import Path
from sys import argv, exit

from cli.constants import IGNORED_DIRS


@dataclass(slots=True)
class FunctionInfo:
    """Information about a function."""

    name: str
    args: list[tuple[str, str]] = field(default_factory=list)
    return_type: str = "None"
    docstring: str = ""
    line: int = 0


@dataclass(slots=True)
class ClassInfo:
    """Information about a class."""

    name: str
    methods: list[FunctionInfo] = field(default_factory=list)
    attributes: list[tuple[str, str]] = field(default_factory=list)
    docstring: str = ""
    line: int = 0


@dataclass(slots=True)
class VariableInfo:
    """Information about a variable."""

    name: str
    type_hint: str
    value: str
    line: int = 0
    is_constant: bool = False


@dataclass(slots=True)
class FileAnalysis:
    """Analysis results for a Python file."""

    file: str
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    variables: list[VariableInfo] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


class TypeAnalyzer:
    """Analyze Python code and extract type information."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def analyze(file_path: Path | str) -> FileAnalysis:
        """Analyze a Python file."""
        path = Path(file_path) if isinstance(file_path, str) else file_path
        analysis: FileAnalysis = FileAnalysis(file=str(path))

        try:
            content: str = path.read_text()
            tree: Module = parse(content)
        except (SyntaxError, UnicodeDecodeError):
            return analysis

        for node in iter_child_nodes(tree):
            match node:
                case ClassDef():
                    analysis.classes.append(TypeAnalyzer._analyze_class(node))
                case FunctionDef() | AsyncFunctionDef():
                    analysis.functions.append(TypeAnalyzer._analyze_function(node))
                case Assign():
                    for target in node.targets:
                        if isinstance(target, Name):
                            analysis.variables.append(
                                TypeAnalyzer._analyze_variable(target, node)
                            )
                case Import():
                    for alias in node.names:
                        analysis.imports.append(alias.name)
                case ImportFrom() if node.module:
                    analysis.imports.append(node.module)
                case _:
                    pass

        return analysis

    @staticmethod
    def _analyze_class(node: ClassDef) -> ClassInfo:
        """Analyze a class node."""
        methods: list[FunctionInfo] = []
        attributes: list[tuple[str, str]] = []

        for item in node.body:
            if isinstance(item, (FunctionDef, AsyncFunctionDef)):
                methods.append(TypeAnalyzer._analyze_function(item))
            elif isinstance(item, AnnAssign) and isinstance(
                item.target,
                Name,
            ):
                attr_type: str = TypeAnalyzer._get_type_annotation(item.annotation)
                attributes.append((item.target.id, attr_type))

        return ClassInfo(
            name=node.name,
            methods=methods,
            attributes=attributes,
            docstring=get_docstring(node) or "",
            line=node.lineno,
        )

    @staticmethod
    def _analyze_function(node: FunctionDef | AsyncFunctionDef) -> FunctionInfo:
        """Analyze a function node."""
        args: list[tuple[str, str]] = []

        for arg in node.args.args:
            arg_name: str = arg.arg
            arg_type: str = TypeAnalyzer._get_type_annotation(arg.annotation)
            args.append((arg_name, arg_type))

        return_type: str = TypeAnalyzer._get_type_annotation(node.returns)

        return FunctionInfo(
            name=node.name,
            args=args,
            return_type=return_type,
            docstring=get_docstring(node) or "",
            line=node.lineno,
        )

    @staticmethod
    def _analyze_variable(
        target: Name,
        node: Assign,
    ) -> VariableInfo:
        """Analyze a variable assignment."""
        name: str = target.id
        # Assign nodes carry no annotation; infer the type from the value.
        type_hint: str = TypeAnalyzer._infer_type(node.value) if node.value else ""
        value: str = dump(node.value) if node.value else ""
        is_constant: bool = name.isupper() and len(name) > 1

        return VariableInfo(
            name=name,
            type_hint=type_hint,
            value=value[:100],  # Truncate long values
            line=node.lineno,
            is_constant=is_constant,
        )

    @staticmethod
    def _get_type_annotation(annotation: expr | None) -> str:
        """Get type annotation as string."""
        match annotation:
            case None:
                return ""
            case Name():
                return annotation.id
            case Constant():
                return str(annotation.value)
            case Subscript():
                base: str = TypeAnalyzer._get_type_annotation(annotation.value)
                inner: str = TypeAnalyzer._get_type_annotation(annotation.slice)
                return f"{base}[{inner}]"
            case BinOp():
                left: str = TypeAnalyzer._get_type_annotation(annotation.left)
                right: str = TypeAnalyzer._get_type_annotation(annotation.right)
                return f"{left} | {right}"
            case Attribute():
                obj: str = TypeAnalyzer._get_type_annotation(annotation.value)
                return f"{obj}.{annotation.attr}"
            case List():
                items: list[str] = [
                    TypeAnalyzer._get_type_annotation(elt) for elt in annotation.elts
                ]
                return f"[{', '.join(items)}]"
            case Tuple():
                parts: list[str] = [
                    TypeAnalyzer._get_type_annotation(elt) for elt in annotation.elts
                ]
                return f"({', '.join(parts)})"
            case _:
                return "object"

    @staticmethod
    def _constant_type(value: object) -> str:
        """Map a constant literal to its type name (bool before int)."""
        match value:
            case bool():
                return "bool"
            case int():
                return "int"
            case float():
                return "float"
            case str():
                return "str"
            case bytes():
                return "bytes"
            case None:
                return "None"
            case _:
                return "object"

    @staticmethod
    def _infer_type(value: expr) -> str:
        """Infer type from a value expression."""
        match value:
            case Constant():
                return TypeAnalyzer._constant_type(value.value)
            case List():
                return "list"
            case Dict():
                return "dict"
            case Set():
                return "set"
            case Tuple():
                return "tuple"
            case Call(func=Name(id=name)):
                return name
            case Call(func=Attribute(attr=attr)):
                return attr
            case Name():
                return value.id
            case Attribute():
                return TypeAnalyzer._infer_type(value.value)
            case _:
                return "object"


def analyze_directory(dir_path: Path) -> list[FileAnalysis]:
    """Analyze all Python files in a directory."""
    analyses: list[FileAnalysis] = []
    for f in sorted(dir_path.rglob("*.py")):
        if any(part in IGNORED_DIRS for part in f.parts):
            continue
        analysis: FileAnalysis = TypeAnalyzer.analyze(f)
        analyses.append(analysis)
    return analyses


def generate_docstring(func_info: FunctionInfo) -> str:
    """Generate a docstring for a function."""
    parts: list[str] = []

    if func_info.args:
        args_str: str = ", ".join(
            [
                f"{name}: {type_hint}"
                for name, type_hint in func_info.args
                if name != "self" and name != "cls"
            ]
        )
        if args_str:
            parts.append(f"Args: {args_str}")

    if func_info.return_type and func_info.return_type != "None":
        parts.append(f"Returns: {func_info.return_type}")

    return "\n".join(parts) if parts else ""


if __name__ == "__main__":
    if len(argv) < 2:
        print("Usage: python -m cli.type_analyzer <file_or_dir>")
        exit(1)

    path: Path = Path(argv[1])
    if path.is_file():
        analysis: FileAnalysis = TypeAnalyzer.analyze(path)
        print(f"File: {analysis.file}")
        print(f"Classes: {len(analysis.classes)}")
        print(f"Functions: {len(analysis.functions)}")
        print(f"Variables: {len(analysis.variables)}")
        print(f"Imports: {len(analysis.imports)}")

        print("\nClasses:")
        for cls in analysis.classes:
            print(f"  {cls.name} (line {cls.line})")
            for method in cls.methods:
                margs: str = ", ".join(a[0] for a in method.args)
                print(f"    {method.name}({margs}) -> {method.return_type}")

        print("\nFunctions:")
        for func in analysis.functions:
            fargs: str = ", ".join(a[0] for a in func.args)
            print(f"  {func.name}({fargs}) -> {func.return_type}")

    elif path.is_dir():
        analyses: list[FileAnalysis] = analyze_directory(path)
        print(f"Analyzed {len(analyses)} files")
        total_classes: int = sum(len(a.classes) for a in analyses)
        total_functions: int = sum(len(a.functions) for a in analyses)
        print(f"Total classes: {total_classes}")
        print(f"Total functions: {total_functions}")
