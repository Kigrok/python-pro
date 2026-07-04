#!/usr/bin/env python3
# cli/performance.py — AST-based performance analysis: weight, complexity, imports.

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from cli.profiler import (
    format_bytes,
)

# Heuristic weights for common third-party packages (bytes).
_IMPORT_WEIGHTS: Final[dict[str, int]] = {
    "numpy": 20_000_000,
    "pandas": 30_000_000,
    "torch": 200_000_000,
    "tensorflow": 300_000_000,
    "sklearn": 15_000_000,
    "scipy": 25_000_000,
    "matplotlib": 15_000_000,
    "flask": 1_000_000,
    "django": 5_000_000,
    "fastapi": 2_000_000,
    "pydantic": 1_500_000,
    "sqlalchemy": 3_000_000,
    "requests": 500_000,
    "httpx": 800_000,
    "aiohttp": 1_000_000,
    "boto3": 5_000_000,
    "click": 300_000,
    "rich": 500_000,
    "typer": 400_000,
    "uvicorn": 600_000,
    "gunicorn": 400_000,
    "celery": 2_000_000,
    "redis": 300_000,
    "pymongo": 800_000,
    "psycopg2": 500_000,
    "pillow": 2_000_000,
    "opencv": 10_000_000,
    "pytest": 2_000_000,
    "mypy": 3_000_000,
    "ruff": 1_000_000,
}


@dataclass(slots=True)
class ImportWeight:
    """Weight analysis for a single import."""

    module: str
    alias: str
    is_stdlib: bool
    estimated_weight: int  # bytes — 0 for stdlib (always loaded)
    line: int

    def __str__(self) -> str:
        origin: str = "stdlib" if self.is_stdlib else "third-party"
        return (
            f"{self.module} as {self.alias}: "
            f"{origin}, ~{format_bytes(self.estimated_weight)}"
        )


@dataclass(slots=True)
class FunctionWeight:
    """AST-based weight analysis for a function."""

    name: str
    line: int
    end_line: int
    args_count: int
    decorators: list[str]
    body_lines: int
    nested_depth: int
    complexity_estimate: int  # rough: branches + loops
    docstring: bool
    annotations_complete: bool
    estimated_weight: str  # human-readable

    def __str__(self) -> str:
        ann: str = "✓" if self.annotations_complete else "✗"
        doc: str = "✓" if self.docstring else "✗"
        return (
            f"{self.name}(L{self.line}-L{self.end_line}): "
            f"args={self.args_count}, body={self.body_lines}L, "
            f"cc≈{self.complexity_estimate}, depth={self.nested_depth}, "
            f"ann={ann}, doc={doc}, ~{self.estimated_weight}"
        )


@dataclass(slots=True)
class ClassWeight:
    """AST-based weight analysis for a class."""

    name: str
    line: int
    end_line: int
    methods: list[FunctionWeight]
    bases: list[str]
    has_slots: bool
    has_init: bool
    body_lines: int
    estimated_weight: str

    def __str__(self) -> str:
        slots: str = "✓" if self.has_slots else "✗"
        return (
            f"{self.name}(L{self.line}-L{self.end_line}): "
            f"{len(self.methods)} methods, {self.body_lines}L, "
            f"slots={slots}, ~{self.estimated_weight}"
        )


@dataclass(slots=True)
class FileProfile:
    """Complete performance profile of a Python file."""

    file: str
    lines: int
    size_bytes: int
    imports: list[ImportWeight]
    functions: list[FunctionWeight]
    classes: list[ClassWeight]
    global_variables: int
    nested_depth_max: int
    total_complexity: int

    @property
    def total_import_weight(self) -> int:
        return sum(i.estimated_weight for i in self.imports)

    @property
    def third_party_count(self) -> int:
        return sum(1 for i in self.imports if not i.is_stdlib)

    def to_compact(self) -> str:
        """Ultra-compact profile."""
        parts: list[str] = []
        parts.append(f"{self.file}: {self.lines}L, {format_bytes(self.size_bytes)}")

        if self.imports:
            tp: int = self.third_party_count
            std: int = len(self.imports) - tp
            imp_w: int = self.total_import_weight
            parts.append(
                f"  imports: {std} stdlib + {tp} third-party "
                f"(~{format_bytes(imp_w)})"
            )

        if self.functions:
            parts.append(f"  functions: {len(self.functions)}")
            worst: FunctionWeight = max(
                self.functions, key=lambda f: f.complexity_estimate
            )
            if worst.complexity_estimate > 5:
                parts.append(
                    f"    most complex: {worst.name}"
                    f"(cc≈{worst.complexity_estimate})"
                )

        if self.classes:
            parts.append(f"  classes: {len(self.classes)}")
            no_slots: list[ClassWeight] = [c for c in self.classes if not c.has_slots]
            if no_slots:
                names: str = ", ".join(c.name for c in no_slots[:3])
                parts.append(f"    missing __slots__: {names}")

        if self.nested_depth_max > 3:
            parts.append(f"  depth: {self.nested_depth_max} (too deep)")

        return "\n".join(parts)

    def to_actions(self) -> list[str]:
        """Suggested performance actions."""
        actions: list[str] = []

        # Heavy imports.
        heavy: list[ImportWeight] = [
            i for i in self.imports if i.estimated_weight > 100_000
        ]
        if heavy:
            names: str = ", ".join(i.module for i in heavy[:3])
            actions.append(f"Lazy-load heavy imports: {names}")

        # Functions without annotations.
        no_ann: list[FunctionWeight] = [
            f for f in self.functions if not f.annotations_complete
        ]
        if no_ann:
            actions.append(f"Add type annotations to {len(no_ann)} function(s)")

        # Complex functions.
        complex_fns: list[FunctionWeight] = [
            f for f in self.functions if f.complexity_estimate > 8
        ]
        if complex_fns:
            names = ", ".join(f.name for f in complex_fns[:3])
            actions.append(f"Refactor complex functions: {names}")

        # Deep nesting.
        if self.nested_depth_max > 3:
            actions.append(f"Reduce nesting depth (max={self.nested_depth_max})")

        # Classes without __slots__.
        no_slots: list[ClassWeight] = [c for c in self.classes if not c.has_slots]
        if no_slots:
            names = ", ".join(c.name for c in no_slots[:3])
            actions.append(f"Add __slots__ to: {names}")

        return actions


_STDLIB_MODULES: Final[frozenset[str]] = frozenset(
    {
        # Python 3.11+ stdlib modules (complete list).
        "abc",
        "argparse",
        "array",
        "ast",
        "asynchat",
        "asyncio",
        "asyncore",
        "atexit",
        "base64",
        "bdb",
        "binascii",
        "binhex",
        "bisect",
        "builtins",
        "bz2",
        "calendar",
        "cgi",
        "cgitb",
        "chunk",
        "cmath",
        "cmd",
        "code",
        "codecs",
        "codeop",
        "collections",
        "colorsys",
        "compileall",
        "concurrent",
        "configparser",
        "contextlib",
        "contextvars",
        "copy",
        "copyreg",
        "cProfile",
        "csv",
        "ctypes",
        "curses",
        "dataclasses",
        "datetime",
        "dbm",
        "decimal",
        "difflib",
        "dis",
        "doctest",
        "email",
        "encodings",
        "enum",
        "errno",
        "faulthandler",
        "fcntl",
        "filecmp",
        "fileinput",
        "fnmatch",
        "fractions",
        "ftplib",
        "functools",
        "gc",
        "getopt",
        "getpass",
        "gettext",
        "glob",
        "grp",
        "gzip",
        "hashlib",
        "heapq",
        "hmac",
        "html",
        "http",
        "idlelib",
        "imaplib",
        "importlib",
        "inspect",
        "io",
        "ipaddress",
        "itertools",
        "json",
        "keyword",
        "linecache",
        "locale",
        "logging",
        "lzma",
        "mailbox",
        "mailcap",
        "marshal",
        "math",
        "mimetypes",
        "mmap",
        "modulefinder",
        "multiprocessing",
        "netrc",
        "numbers",
        "operator",
        "os",
        "pathlib",
        "pdb",
        "pickle",
        "pickletools",
        "pipes",
        "pkgutil",
        "platform",
        "plistlib",
        "poplib",
        "posix",
        "posixpath",
        "pprint",
        "profile",
        "pstats",
        "pty",
        "pwd",
        "py_compile",
        "pyclbr",
        "pydoc",
        "queue",
        "quopri",
        "random",
        "re",
        "reprlib",
        "resource",
        "rlcompleter",
        "runpy",
        "sched",
        "secrets",
        "select",
        "selectors",
        "shelve",
        "shlex",
        "shutil",
        "signal",
        "site",
        "smtplib",
        "socket",
        "socketserver",
        "sqlite3",
        "sre_compile",
        "sre_constants",
        "sre_parse",
        "ssl",
        "stat",
        "statistics",
        "string",
        "stringprep",
        "struct",
        "subprocess",
        "symtable",
        "sys",
        "sysconfig",
        "syslog",
        "tabnanny",
        "tarfile",
        "tempfile",
        "termios",
        "test",
        "textwrap",
        "threading",
        "time",
        "timeit",
        "tkinter",
        "token",
        "tokenize",
        "trace",
        "traceback",
        "tracemalloc",
        "tty",
        "turtle",
        "turtledemo",
        "types",
        "typing",
        "unicodedata",
        "unittest",
        "urllib",
        "uu",
        "uuid",
        "venv",
        "warnings",
        "wave",
        "weakref",
        "webbrowser",
        "xml",
        "xmlrpc",
        "zipapp",
        "zipfile",
        "zipimport",
        "zlib",
        # Python 3.11+ additions.
        "tomllib",
        "graphlib",
        "zoneinfo",
        "typing_extensions",
        "_thread",
        # Internal/underscore modules.
        "_aio",
    }
)


class PerformanceAnalyzer:
    """AST-based performance analysis for Python files."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def _estimate_import_weight(module: str) -> int:
        """Estimate memory weight of importing a module in bytes."""
        if module in _STDLIB_MODULES or module.split(".")[0] in _STDLIB_MODULES:
            return 0  # stdlib is always loaded

        top: str = module.split(".")[0]
        return _IMPORT_WEIGHTS.get(top, 200_000)  # default 200KB for unknown

    @staticmethod
    def _count_nested_depth(node: ast.AST, depth: int = 0) -> int:
        """Find maximum nesting depth."""
        max_depth: int = depth
        for child in ast.iter_child_nodes(node):
            if isinstance(
                child,
                (
                    ast.If,
                    ast.For,
                    ast.While,
                    ast.With,
                    ast.Try,
                    ast.AsyncFor,
                    ast.AsyncWith,
                ),
            ):
                child_depth: int = PerformanceAnalyzer._count_nested_depth(
                    child,
                    depth + 1,
                )
                if child_depth > max_depth:
                    max_depth = child_depth
            else:
                child_depth = PerformanceAnalyzer._count_nested_depth(child, depth)
                if child_depth > max_depth:
                    max_depth = child_depth
        return max_depth

    @staticmethod
    def _estimate_complexity(node: ast.AST) -> int:
        """Rough cyclomatic complexity from AST (branches + loops)."""
        cc: int = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.ExceptHandler)):
                cc += 1
            elif isinstance(child, (ast.For, ast.While, ast.AsyncFor)):
                cc += 2
            elif isinstance(child, ast.BoolOp):
                cc += len(child.values) - 1
            elif isinstance(child, ast.Assert):
                cc += 1
        return cc

    @staticmethod
    def _analyze_function(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> FunctionWeight:
        """Analyze a single function."""
        args: ast.arguments = node.args
        all_args: list[ast.arg] = args.posonlyargs + args.args + args.kwonlyargs
        args_count: int = len(all_args)

        decorators: list[str] = []
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                decorators.append(dec.id)
            elif isinstance(dec, ast.Attribute):
                decorators.append(dec.attr)
            elif isinstance(dec, ast.Call):
                if isinstance(dec.func, ast.Name):
                    decorators.append(dec.func.id)
                elif isinstance(dec.func, ast.Attribute):
                    decorators.append(dec.func.attr)

        body_lines: int = (node.end_lineno or node.lineno) - node.lineno + 1
        nested: int = PerformanceAnalyzer._count_nested_depth(node)
        cc: int = PerformanceAnalyzer._estimate_complexity(node)

        docstring: bool = bool(ast.get_docstring(node))

        # Check annotations completeness.
        has_return: bool = node.returns is not None
        all_annotated: bool = all(a.annotation is not None for a in all_args)
        annotations_complete: bool = has_return and all_annotated

        # Estimate weight.
        weight: int = body_lines * 50  # rough: 50 bytes per line of code
        weight += args_count * 8  # each arg ~8 bytes reference
        if docstring:
            doc_node = node.body[0] if node.body else None
            if isinstance(doc_node, ast.Expr) and isinstance(
                doc_node.value, ast.Constant
            ):
                weight += len(str(doc_node.value.value))

        return FunctionWeight(
            name=node.name,
            line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            args_count=args_count,
            decorators=decorators,
            body_lines=body_lines,
            nested_depth=nested,
            complexity_estimate=cc,
            docstring=docstring,
            annotations_complete=annotations_complete,
            estimated_weight=format_bytes(weight),
        )

    @staticmethod
    def _is_dataclass_decorator(decorator: ast.expr) -> bool:
        """True if a decorator is `dataclass` or `dataclass(...)`."""
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name):
            return target.id == "dataclass"
        if isinstance(target, ast.Attribute):
            return target.attr == "dataclass"
        return False

    @staticmethod
    def _analyze_class(node: ast.ClassDef) -> ClassWeight:
        """Analyze a single class."""
        methods: list[FunctionWeight] = []
        # A @dataclass(slots=True) generates __slots__ itself, so treat any
        # @dataclass as already slotted rather than flagging it.
        has_slots: bool = any(
            PerformanceAnalyzer._is_dataclass_decorator(d) for d in node.decorator_list
        )
        has_init: bool = False

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(PerformanceAnalyzer._analyze_function(item))
                if item.name == "__init__":
                    has_init = True
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "__slots__":
                        has_slots = True
            elif (
                isinstance(item, ast.AnnAssign)
                and isinstance(item.target, ast.Name)
                and item.target.id == "__slots__"
            ):
                has_slots = True

        bases: list[str] = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(base.attr)

        # Enums, pydantic and ORM base classes are not meaningfully slottable;
        # do not flag them as "missing __slots__".
        if any(kw in b for b in bases for kw in ("Enum", "Base", "Protocol")):
            has_slots = True

        body_lines: int = (node.end_lineno or node.lineno) - node.lineno + 1
        weight: int = body_lines * 30  # class overhead
        weight += len(methods) * 200  # per method overhead
        if not has_slots:
            weight += 1000  # penalty for missing __slots__

        return ClassWeight(
            name=node.name,
            line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            methods=methods,
            bases=bases,
            has_slots=has_slots,
            has_init=has_init,
            body_lines=body_lines,
            estimated_weight=format_bytes(weight),
        )

    @staticmethod
    def analyze(file_path: str) -> FileProfile:
        """Full performance profile of a Python file."""
        path: Path = Path(file_path)
        source: str = path.read_text(encoding="utf-8", errors="replace")
        lines: int = source.count("\n") + 1
        size_bytes: int = path.stat().st_size

        tree: ast.Module = ast.parse(source, filename=file_path)

        # Imports.
        imports: list[ImportWeight] = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod: str = alias.name
                    alias_name: str = alias.asname or alias.name
                    imports.append(
                        ImportWeight(
                            module=mod,
                            alias=alias_name,
                            is_stdlib=mod in _STDLIB_MODULES
                            or mod.split(".")[0] in _STDLIB_MODULES,
                            estimated_weight=PerformanceAnalyzer._estimate_import_weight(
                                mod
                            ),
                            line=node.lineno,
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for alias in node.names:
                    full_mod: str = f"{mod}.{alias.name}" if mod else alias.name
                    alias_name = alias.asname or alias.name
                    imports.append(
                        ImportWeight(
                            module=full_mod,
                            alias=alias_name,
                            is_stdlib=mod in _STDLIB_MODULES
                            or mod.split(".")[0] in _STDLIB_MODULES,
                            estimated_weight=PerformanceAnalyzer._estimate_import_weight(
                                mod
                            ),
                            line=node.lineno,
                        )
                    )

        # Functions and classes.
        functions: list[FunctionWeight] = []
        classes: list[ClassWeight] = []
        global_vars: int = 0

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(PerformanceAnalyzer._analyze_function(node))
            elif isinstance(node, ast.ClassDef):
                classes.append(PerformanceAnalyzer._analyze_class(node))
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                global_vars += 1

        # Global nesting depth.
        depth_max: int = PerformanceAnalyzer._count_nested_depth(tree)

        # Total complexity.
        total_cc: int = sum(f.complexity_estimate for f in functions)

        return FileProfile(
            file=file_path,
            lines=lines,
            size_bytes=size_bytes,
            imports=imports,
            functions=functions,
            classes=classes,
            global_variables=global_vars,
            nested_depth_max=depth_max,
            total_complexity=total_cc,
        )

    @staticmethod
    def import_weights(file_path: str) -> list[ImportWeight]:
        """Get import weights for a file."""
        profile: FileProfile = PerformanceAnalyzer.analyze(file_path)
        return sorted(profile.imports, key=lambda i: -i.estimated_weight)

    @staticmethod
    def function_weights(file_path: str) -> list[FunctionWeight]:
        """Get function weights for a file."""
        profile: FileProfile = PerformanceAnalyzer.analyze(file_path)
        return sorted(profile.functions, key=lambda f: -f.complexity_estimate)

    @staticmethod
    def file_weight(file_path: str) -> dict[str, object]:
        """Get complete weight breakdown for a file."""
        profile: FileProfile = PerformanceAnalyzer.analyze(file_path)
        return {
            "file": profile.file,
            "lines": profile.lines,
            "size_bytes": profile.size_bytes,
            "size_human": format_bytes(profile.size_bytes),
            "imports": len(profile.imports),
            "third_party": profile.third_party_count,
            "import_weight": format_bytes(profile.total_import_weight),
            "functions": len(profile.functions),
            "classes": len(profile.classes),
            "global_vars": profile.global_variables,
            "max_depth": profile.nested_depth_max,
            "total_cc": profile.total_complexity,
        }
