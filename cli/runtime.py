#!/usr/bin/env python3
# cli/runtime.py — Safe code execution with error capture + logging.

from __future__ import annotations

import ast
import signal
from dataclasses import dataclass
from logging import Logger, getLogger
from pathlib import Path
from sys import exc_info
from time import perf_counter, perf_counter_ns, time
from traceback import format_tb
from typing import Final

log: Final[Logger] = getLogger("python-pro.runtime")

# Safe builtins — restrict dangerous operations.
# Includes __import__, __build_class__, __name__ for module/class execution.
_SAFE_BUILTINS: Final[dict[str, object]] = {
    "__import__": (
        __builtins__["__import__"]
        if isinstance(__builtins__, dict)
        else __builtins__.__import__
    ),
    "__build_class__": (
        __builtins__["__build_class__"]
        if isinstance(__builtins__, dict)
        else __builtins__.__build_class__
    ),
    "__name__": "__main__",
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "bytearray": bytearray,
    "bytes": bytes,
    "callable": callable,
    "chr": chr,
    "complex": complex,
    "dict": dict,
    "dir": dir,
    "divmod": divmod,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "format": format,
    "frozenset": frozenset,
    "getattr": getattr,
    "globals": globals,
    "hasattr": hasattr,
    "hash": hash,
    "hex": hex,
    "id": id,
    "int": int,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "iter": iter,
    "len": len,
    "list": list,
    "locals": locals,
    "map": map,
    "max": max,
    "memoryview": memoryview,
    "min": min,
    "next": next,
    "object": object,
    "oct": oct,
    "ord": ord,
    "pow": pow,
    "print": print,
    "property": property,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "staticmethod": staticmethod,
    "str": str,
    "sum": sum,
    "super": super,
    "tuple": tuple,
    "type": type,
    "vars": vars,
    "zip": zip,
}


class TimeoutError(Exception):
    """Raised when execution exceeds timeout."""


def _timeout_handler(signum: int, frame: object) -> None:
    """Signal handler for timeout."""
    raise TimeoutError("Execution timed out")


@dataclass(slots=True)
class RuntimeError_:
    """Captured runtime error with full context."""

    file: str
    line: int
    col: int
    error_type: str
    message: str
    source_line: str
    locals_snapshot: dict[str, str]  # name -> repr(value)
    traceback_text: str
    timestamp: float = 0.0

    def to_compact(self) -> str:
        """Ultra-compact error format for AI."""
        locs: str = ""
        if self.locals_snapshot:
            items: list[str] = [
                f"{k}={v}" for k, v in list(self.locals_snapshot.items())[:5]
            ]
            locs = f" | vars: {', '.join(items)}"
        return (
            f"[RUNTIME ERROR] {self.file}:{self.line}:{self.col} "
            f"| {self.error_type}: {self.message}"
            f"{locs}"
        )

    def to_full(self) -> str:
        """Full error context for debugging."""
        lines: list[str] = []
        lines.append(f"Error: {self.error_type}: {self.message}")
        lines.append(f"File: {self.file}:{self.line}:{self.col}")
        lines.append(f"Source: {self.source_line}")
        if self.locals_snapshot:
            lines.append("Variables at error point:")
            for k, v in self.locals_snapshot.items():
                lines.append(f"  {k} = {v}")
        if self.traceback_text:
            lines.append("Traceback:")
            lines.append(self.traceback_text)
        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        """Dictionary format for JSON output."""
        return {
            "file": self.file,
            "line": self.line,
            "col": self.col,
            "error_type": self.error_type,
            "message": self.message,
            "source_line": self.source_line,
            "locals": self.locals_snapshot,
            "traceback": self.traceback_text,
        }


@dataclass(slots=True)
class RuntimeWarning_:
    """Non-error issue detected at runtime."""

    file: str
    line: int
    warning_type: str  # "deprecation", "type_mismatch", "unused", "perf"
    message: str
    details: str = ""

    def to_compact(self) -> str:
        return f"[WARN] {self.file}:{self.line} | {self.warning_type}: {self.message}"


@dataclass(slots=True)
class RuntimeProfile:
    """Performance profile from a single execution run."""

    file: str
    execution_time_ms: float
    memory_peak_bytes: int
    warnings: list[RuntimeWarning_]
    errors: list[RuntimeError_]

    @property
    def has_issues(self) -> bool:
        return bool(self.warnings) or bool(self.errors)

    def to_compact(self) -> str:
        parts: list[str] = []
        parts.append(f"[RUNTIME] {self.file}: {self.execution_time_ms:.1f}ms")
        for e in self.errors[:5]:
            parts.append(f"  {e.to_compact()}")
        for w in self.warnings[:5]:
            parts.append(f"  {w.to_compact()}")
        return "\n".join(parts)


class RuntimeExecutor:
    """Safe execution of Python code with error capture."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def _extract_source_line(file_path: str, line: int) -> str:
        """Get the source line that caused the error."""
        try:
            lines: list[str] = (
                Path(file_path)
                .read_text(
                    encoding="utf-8",
                    errors="replace",
                )
                .splitlines()
            )
            if 0 < line <= len(lines):
                return lines[line - 1].strip()
        except (OSError, IndexError):
            pass
        return ""

    @staticmethod
    def _capture_locals(frame: object) -> dict[str, str]:
        """Capture local variables at error point."""
        if frame is None:
            return {}
        result: dict[str, str] = {}
        for name, value in frame.f_locals.items():
            if name.startswith("_"):
                continue
            try:
                result[name] = repr(value)[:100]  # truncate long reprs
            except Exception:
                # repr() of an arbitrary user object may raise anything.
                result[name] = "<unrepresentable>"
        return result

    @staticmethod
    def execute_file(
        file_path: str,
        timeout: float = 10.0,
    ) -> RuntimeProfile:
        """Execute a Python file and capture all issues."""
        log.info("RuntimeExecutor.execute_file: %s (timeout=%s)", file_path, timeout)
        path: Path = Path(file_path)

        if not path.exists():
            log.warning("File not found: %s", file_path)
            return RuntimeProfile(
                file=file_path,
                execution_time_ms=0,
                memory_peak_bytes=0,
                warnings=[],
                errors=[],
            )

        import tracemalloc

        tracemalloc.start()

        errors: list[RuntimeError_] = []
        warnings: list[RuntimeWarning_] = []
        t0: float = perf_counter()

        try:
            source: str = path.read_text(encoding="utf-8", errors="replace")

            # Compile and check for syntax errors first.
            try:
                code = compile(source, file_path, "exec")
            except SyntaxError as exc:
                elapsed: float = (perf_counter() - t0) * 1000
                tracemalloc.stop()
                errors.append(
                    RuntimeError_(
                        file=file_path,
                        line=exc.lineno or 0,
                        col=exc.offset or 0,
                        error_type="SyntaxError",
                        message=exc.msg,
                        source_line=RuntimeExecutor._extract_source_line(
                            file_path,
                            exc.lineno or 0,
                        ),
                        locals_snapshot={},
                        traceback_text="",
                        timestamp=time(),
                    )
                )
                log.error("SyntaxError in %s:%d: %s", file_path, exc.lineno, exc.msg)
                return RuntimeProfile(
                    file=file_path,
                    execution_time_ms=elapsed,
                    memory_peak_bytes=0,
                    warnings=warnings,
                    errors=errors,
                )

            # Check for common issues in AST.
            tree: ast.Module = ast.parse(source, filename=file_path)
            ast_warnings: list[RuntimeWarning_] = RuntimeExecutor._check_ast(
                tree,
                file_path,
                source,
            )
            warnings.extend(ast_warnings)

            # Execute with timeout (via signal if available).
            namespace: dict[str, object] = {
                "__name__": "__main__",
                "__file__": file_path,
                "__builtins__": _SAFE_BUILTINS,
            }
            # Set timeout if supported (Unix only).
            old_handler = None
            try:
                old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
                signal.alarm(int(timeout))
            except (AttributeError, ValueError):
                pass  # Windows or invalid timeout.

            try:
                exec(code, namespace)
            finally:
                # Reset alarm.
                try:
                    signal.alarm(0)
                    if old_handler is not None:
                        signal.signal(signal.SIGALRM, old_handler)
                except (AttributeError, ValueError):
                    pass

        except Exception as exc:
            elapsed = (perf_counter() - t0) * 1000
            _, _, tb = exc_info()
            tb_text: str = "".join(format_tb(tb))
            frame: object = tb.tb_frame if tb else None

            # Find the innermost frame in our file.
            while tb:
                if tb.tb_frame.f_code.co_filename == file_path:
                    frame = tb.tb_frame
                    break
                tb = tb.tb_next

            errors.append(
                RuntimeError_(
                    file=file_path,
                    line=tb.tb_lineno if tb else 0,
                    col=0,
                    error_type=type(exc).__name__,
                    message=str(exc),
                    source_line=RuntimeExecutor._extract_source_line(
                        file_path,
                        tb.tb_lineno if tb else 0,
                    ),
                    locals_snapshot=RuntimeExecutor._capture_locals(frame),
                    traceback_text=tb_text,
                    timestamp=time(),
                )
            )
            log.error(
                "Runtime error in %s:%d: %s: %s",
                file_path,
                tb.tb_lineno if tb else 0,
                type(exc).__name__,
                exc,
            )
        finally:
            tracemalloc.stop()

        elapsed = (perf_counter() - t0) * 1000
        _, peak = tracemalloc.get_traced_memory()

        log.info(
            "Execution complete: %s (%.1fms, errors=%d, warnings=%d)",
            file_path,
            elapsed,
            len(errors),
            len(warnings),
        )

        return RuntimeProfile(
            file=file_path,
            execution_time_ms=elapsed,
            memory_peak_bytes=peak,
            warnings=warnings,
            errors=errors,
        )

    @staticmethod
    def execute_function(
        code: str,
        function_name: str,
        args: list[str] | None = None,
        kwargs: dict[str, str] | None = None,
    ) -> dict[str, object]:
        """Execute a specific function and capture result."""
        log.info(
            "RuntimeExecutor.execute_function: %s (args=%s, kwargs=%s)",
            function_name,
            args,
            kwargs,
        )
        result: dict[str, object] = {
            "function": function_name,
            "success": False,
            "result": None,
            "error": None,
            "execution_time_ms": 0.0,
        }

        try:
            tree = ast.parse(code)
            # Find the function.
            func_node: ast.FunctionDef | None = None
            for node in ast.iter_child_nodes(tree):
                if (
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == function_name
                ):
                    func_node = node
                    break

            if func_node is None:
                result["error"] = f"Function {function_name!r} not found"
                return result

            # Compile the whole module.
            compiled = compile(tree, "<string>", "exec")
            namespace: dict[str, object] = {}
            exec(compiled, namespace)

            func = namespace.get(function_name)
            if func is None:
                result["error"] = f"Function {function_name!r} not found after exec"
                return result

            # Parse args.
            import json as _json

            parsed_args: list[object] = []
            if args:
                for a in args:
                    try:
                        parsed_args.append(_json.loads(a))
                    except (_json.JSONDecodeError, ValueError):
                        parsed_args.append(a)

            parsed_kwargs: dict[str, object] = {}
            if kwargs:
                for k, v in kwargs.items():
                    try:
                        parsed_kwargs[k] = _json.loads(v)
                    except (_json.JSONDecodeError, ValueError):
                        parsed_kwargs[k] = v

            # Execute.
            t0 = perf_counter_ns()
            call_result = func(*parsed_args, **parsed_kwargs)
            elapsed_ns: int = perf_counter_ns() - t0

            result["success"] = True
            result["result"] = repr(call_result)[:500]
            result["execution_time_ms"] = elapsed_ns / 1_000_000

        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
            log.error("Function execution failed: %s", exc)

        return result

    @staticmethod
    def _check_ast(
        tree: ast.Module,
        file_path: str,
        source: str,
    ) -> list[RuntimeWarning_]:
        """Check AST for common issues."""
        warnings: list[RuntimeWarning_] = []

        for node in ast.walk(tree):
            # Bare except.
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                warnings.append(
                    RuntimeWarning_(
                        file=file_path,
                        line=node.lineno,
                        warning_type="bad_practice",
                        message="Bare except — use except Exception at minimum",
                    )
                )

            # Mutable default argument.
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for default in node.args.defaults + node.args.kw_defaults:
                    if default and isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        warnings.append(
                            RuntimeWarning_(
                                file=file_path,
                                line=node.lineno,
                                warning_type="mutable_default",
                                message=f"Mutable default argument in {node.name}()",
                            )
                        )

            # isinstance with more than 3 types.
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "isinstance"
                and len(node.args) > 1
            ):
                second = node.args[1]
                if isinstance(second, ast.Tuple) and len(second.elts) > 3:
                    warnings.append(
                        RuntimeWarning_(
                            file=file_path,
                            line=node.lineno,
                            warning_type="complex_check",
                            message=f"isinstance with {len(second.elts)} types — use match/case",
                        )
                    )

            # String concatenation in loop.
            if isinstance(node, (ast.For, ast.While)):
                for child in ast.walk(node):
                    if (
                        isinstance(child, ast.AugAssign)
                        and isinstance(child.op, ast.Add)
                        and isinstance(child.value, (ast.Constant, ast.JoinedStr))
                    ):
                        warnings.append(
                            RuntimeWarning_(
                                file=file_path,
                                line=child.lineno,
                                warning_type="perf",
                                message="String concatenation in loop — use join()",
                            )
                        )
                        break

        return warnings


class FileRunner:
    """Run a file and return structured results."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def run(file_path: str) -> str:
        """Run file, return compact error report."""
        profile: RuntimeProfile = RuntimeExecutor.execute_file(file_path)
        if not profile.has_issues:
            return f"[OK] {file_path}: executed in {profile.execution_time_ms:.1f}ms"
        return profile.to_compact()

    @staticmethod
    def run_function(
        file_path: str,
        function_name: str,
        args: list[str] | None = None,
        kwargs: dict[str, str] | None = None,
    ) -> str:
        """Run a specific function, return result."""
        source: str = Path(file_path).read_text(encoding="utf-8", errors="replace")
        result: dict[str, object] = RuntimeExecutor.execute_function(
            source,
            function_name,
            args,
            kwargs,
        )
        if result["success"]:
            return (
                f"[OK] {function_name}(): {result['result']} "
                f"({result['execution_time_ms']:.1f}ms)"
            )
        return f"[ERROR] {function_name}(): {result['error']}"

    @staticmethod
    def check_syntax(file_path: str) -> str:
        """Check syntax and report with source context."""
        try:
            source: str = Path(file_path).read_text(encoding="utf-8", errors="replace")
            compile(source, file_path, "exec")
            return f"[OK] {file_path}: syntax valid"
        except SyntaxError as exc:
            line: int = exc.lineno or 0
            source_line: str = ""
            try:
                lines: list[str] = source.splitlines()
                if 0 < line <= len(lines):
                    source_line = lines[line - 1]
            except (OSError, IndexError):
                pass
            return (
                f"[SYNTAX ERROR] {file_path}:{line}:{exc.offset or 0}\n"
                f"  {exc.msg}\n"
                f"  → {source_line}"
            )
