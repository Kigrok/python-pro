#!/usr/bin/env python3
# mcp_server/server.py — MCP tools for python-pro linting and skill detection.

from __future__ import annotations

from asyncio import gather, run
from json import dumps
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from cli.annotation_fixer import AnnotationReporter, MissingAnnotation
from cli.codegen import CodeGenEngine
from cli.codegraph import CodeGraph
from cli.codemods import CodeFormatter, CodemodEngine, DeadCodeAnalyzer, ImportSorter
from cli.deps import StdlibFirstChecker
from cli.fixer import FixOutcome
from cli.linters import run_linters, run_linters_batch
from cli.metrics import ComplexityAnalyzer
from cli.models import FileReport, LinterResult, LintError
from cli.optimizations import (
    ast_cache_stats,
    detect_refactor_opportunities,
    get_stale_files,
    lazy_import_stats,
    mcp_cache,
    mcp_cache_clear,
    metrics_summary,
    parse_ast_cached,
    profiling_disable,
    profiling_enable,
    profiling_is_enabled,
    profiling_snapshot,
)
from cli.outline import Outline
from cli.performance import PerformanceAnalyzer
from cli.pipeline import DeterministicPipeline, PipelineResult
from cli.pre_commit import PreCommitFixer
from cli.profiler import (
    clear_stats,
    format_bytes,
    get_memory_stats,
    get_timing_stats,
    object_weight,
)
from cli.prompts import (
    SKILL_INSTRUCTIONS,
    DeadCodePromptBuilder,
    PromptBuilder,
    RefactorPromptBuilder,
    get_instruction,
)
from cli.runner import TestRunner
from cli.runtime import FileRunner, RuntimeExecutor, RuntimeProfile
from cli.scaffolder import Scaffolder
from cli.security import SecurityScanner
from cli.smart_context import SmartContextBuilder
from cli.type_analyzer import FileAnalysis, TypeAnalyzer, generate_docstring
from cli.validator import PythonProValidator, ValidationReport
from memory import PatternStorage
from skills.detector import CodeAnalyzer, SkillDetector

app: Server = Server("python-pro")
_graph: CodeGraph | None = None


def _get_graph() -> CodeGraph:
    """Get or build the code graph (cached per session)."""
    global _graph
    if _graph is None:
        _graph = CodeGraph.load()
    return _graph


class ReportFormatter:
    """Formats FileReport for text and JSON output."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def to_text(report: FileReport) -> str:
        """Convert report to compact text format."""
        if not report.has_errors:
            return f"{report.file}: no errors found"
        lines: list[str] = [
            f"{report.file}: {report.total_errors} errors",
        ]
        error: LintError
        for error in report.all_errors():
            lines.append(f"  {error.compact}")
        return "\n".join(lines)

    @staticmethod
    def to_dict(report: FileReport) -> dict[str, object]:
        """Convert report to dictionary."""
        return {
            "file": report.file,
            "total_errors": report.total_errors,
            "errors": [
                {
                    "line": e.line,
                    "col": e.col,
                    "code": e.code,
                    "message": e.message,
                    "linter": e.linter,
                    "severity": e.severity.value,
                }
                for e in report.all_errors()
            ],
        }

    @staticmethod
    def to_json(report: FileReport) -> str:
        """Convert report to JSON string."""
        return dumps(ReportFormatter.to_dict(report), indent=2)


class MCPTools:
    """MCP tool implementations for python-pro."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def _str_list(value: object) -> list[str]:
        """Coerce a tool argument to a list of strings."""
        return [str(v) for v in value] if isinstance(value, list) else []

    @staticmethod
    def _as_int(value: object, default: int = 0) -> int:
        """Coerce a tool argument to int."""
        return value if isinstance(value, int) else default

    @staticmethod
    async def lint_and_fix(
        file_path: str,
        linters: list[str] | None = None,
    ) -> str:
        """Run linters + auto-fix pipeline. Returns lint report + residue."""
        # Run fix first (codemods + ruff + black).
        fix_result: PipelineResult = await DeterministicPipeline.run(file_path)
        fix_summary: str = fix_result.summary()

        # Then run linters for full report.
        results: list[LinterResult] = await run_linters(file_path, linters)
        report: FileReport = FileReport(file=file_path, results=results)
        lint_text: str = ReportFormatter.to_text(report)

        # Combine: lint report first, then residue.
        parts: list[str] = []
        if lint_text:
            parts.append(lint_text)
        if fix_summary:
            parts.append(f"\nResidue after auto-fix:\n{fix_summary}")
        elif fix_result.outcome.changed:
            parts.append(f"\nAuto-fix applied: {file_path}")
        return "\n".join(parts) if parts else f"{file_path}: clean"

    @staticmethod
    async def lint_file(
        file_path: str,
        linters: list[str] | None = None,
    ) -> str:
        """Run linters on a file and return text report."""
        results: list[LinterResult] = await run_linters(
            file_path,
            linters,
        )
        report: FileReport = FileReport(
            file=file_path,
            results=results,
        )
        return ReportFormatter.to_text(report)

    @staticmethod
    async def fix_file(file_path: str) -> str:
        """Run the deterministic pipeline; return only the unfixable residue."""
        result: PipelineResult = await DeterministicPipeline.run(file_path)
        summary: str = result.summary()
        if summary:
            return summary
        note: str = "changed" if result.outcome.changed else "already clean"
        return f"{file_path}: no issues after auto-fix ({note})"

    @staticmethod
    @mcp_cache(ttl=5.0)
    def check_syntax(file_path: str) -> str:
        """Check syntax of a file."""
        try:
            compile(
                Path(file_path).read_text(),
                file_path,
                "exec",
            )
            return f"{file_path}: syntax OK"
        except SyntaxError as exc:
            return f"{file_path}: {exc}"

    @staticmethod
    async def lint_batch(
        file_paths: list[str],
    ) -> str:
        """Lint multiple files and return combined report."""
        all_results: dict[str, list[LinterResult]] = await run_linters_batch(file_paths)
        lines: list[str] = []
        total: int = 0
        fp: str
        results: list[LinterResult]
        for fp, results in all_results.items():
            report: FileReport = FileReport(
                file=fp,
                results=results,
            )
            total += report.total_errors
            lines.append(ReportFormatter.to_text(report))
            lines.append("")

        header: str = f"Batch: {len(file_paths)} files, {total} total errors"
        return header + "\n\n" + "\n".join(lines)

    @staticmethod
    @mcp_cache(ttl=5.0)
    def validate_file(file_path: str) -> str:
        """Validate file against python-pro rules."""
        report: ValidationReport = PythonProValidator.validate(
            Path(file_path),
        )
        if not report.issues:
            return f"{file_path}: all rules passed"

        lines: list[str] = [f"{file_path}: {len(report.issues)} issues"]
        issue: object
        for issue in report.issues:
            icon: str = "❌" if issue.severity == "error" else "⚠️"
            lines.append(f"  {icon} Line {issue.line}: [{issue.rule}] {issue.message}")
        return "\n".join(lines)

    @staticmethod
    @mcp_cache(ttl=5.0)
    def validate_batch(file_paths: list[str]) -> str:
        """Validate multiple files against python-pro rules."""
        all_issues: int = 0
        lines: list[str] = []

        fp: str
        for fp in file_paths:
            report: ValidationReport = PythonProValidator.validate(
                Path(fp),
            )
            if report.issues:
                all_issues += len(report.issues)
                lines.append(f"\n{fp}: {len(report.issues)} issues")
                issue: object
                for issue in report.issues:
                    icon: str = "❌" if issue.severity == "error" else "⚠️"
                    lines.append(
                        f"  {icon} Line {issue.line}: [{issue.rule}] {issue.message}"
                    )

        header: str = f"Batch: {len(file_paths)} files, {all_issues} total issues"
        return header + "\n".join(lines)

    @staticmethod
    @mcp_cache(ttl=5.0)
    def analyze_types(file_path: str) -> str:
        """Analyze types in a Python file."""
        analysis: FileAnalysis = TypeAnalyzer.analyze(Path(file_path))

        lines: list[str] = [f"File: {analysis.file}"]
        lines.append(f"Classes: {len(analysis.classes)}")
        lines.append(f"Functions: {len(analysis.functions)}")
        lines.append(f"Variables: {len(analysis.variables)}")
        lines.append("")

        if analysis.classes:
            lines.append("Classes:")
            cls: object
            for cls in analysis.classes:
                lines.append(f"  {cls.name} (line {cls.line})")
                method: object
                for method in cls.methods:
                    args_str: str = ", ".join(
                        [
                            f"{a[0]}: {a[1]}"
                            for a in method.args
                            if a[0] not in ("self", "cls")
                        ]
                    )
                    lines.append(
                        f"    {method.name}({args_str}) -> {method.return_type}"
                    )

        if analysis.functions:
            lines.append("Functions:")
            func: object
            for func in analysis.functions:
                args_str = ", ".join(
                    [
                        f"{a[0]}: {a[1]}"
                        for a in func.args
                        if a[0] not in ("self", "cls")
                    ]
                )
                lines.append(f"  {func.name}({args_str}) -> {func.return_type}")

        return "\n".join(lines)

    @staticmethod
    def generate_docstrings(file_path: str) -> str:
        """Generate docstrings with type info for a file."""
        analysis: FileAnalysis = TypeAnalyzer.analyze(Path(file_path))

        lines: list[str] = []
        func: object
        for func in analysis.functions:
            docstring: str = generate_docstring(func)
            if docstring:
                args_str: str = ", ".join(
                    [a[0] for a in func.args if a[0] not in ("self", "cls")]
                )
                lines.append(f"def {func.name}({args_str}):")
                lines.append('    """')
                lines.append(f"    {docstring}")
                lines.append('    """')
                lines.append("")

        return "\n".join(lines) if lines else "No docstrings to generate"

    @staticmethod
    @mcp_cache(ttl=5.0)
    def check_annotations(file_path: str) -> str:
        """Report variables missing type annotations (no file writes)."""
        issues: list[MissingAnnotation] = AnnotationReporter.check_file(
            Path(file_path),
        )
        if not issues:
            return f"{file_path}: all variables annotated"
        lines: list[str] = [
            f"{file_path}: {len(issues)} missing annotations",
        ]
        issue: MissingAnnotation
        for issue in issues:
            hint: str = f" -> {issue.suggestion}" if issue.suggestion else ""
            lines.append(f"  line {issue.line}: {issue.name} [{issue.scope}]{hint}")
        return "\n".join(lines)

    @staticmethod
    def get_patterns(min_count: int = 1) -> str:
        """Report frequent linter error patterns learned by the hook."""
        frequent: list[dict[str, object]] = PatternStorage.get_frequent(
            min_count,
        )
        if not frequent:
            return "No recorded error patterns yet"
        lines: list[str] = [f"{len(frequent)} recorded patterns:"]
        entry: dict[str, object]
        for entry in sorted(frequent, key=lambda e: -MCPTools._as_int(e["count"])):
            lines.append(
                f"  {entry['linter']} {entry['code']}: "
                f"{entry['message']} (seen {entry['count']}x)"
            )
        return "\n".join(lines)

    @staticmethod
    async def fix_batch(file_paths: list[str]) -> str:
        """Fix multiple files in parallel; return per-file residue."""
        results: list[PipelineResult] = await gather(
            *(DeterministicPipeline.run(fp) for fp in file_paths)
        )
        total: int = sum(r.residual_count for r in results)
        lines: list[str] = []
        res: PipelineResult
        for res in results:
            lines.append(res.summary() or f"{res.file}: clean after auto-fix")
        header: str = (
            f"Batch: {len(file_paths)} files, "
            f"{total} issue(s) remain after auto-fix"
        )
        return header + "\n\n" + "\n".join(lines)

    @staticmethod
    def summary(file_path: str) -> str:
        """One-line status for a file (token-saver)."""
        result: PipelineResult = PipelineResult(file=file_path, outcome=FixOutcome())
        return result.one_line()

    @staticmethod
    async def smart_context(file_path: str) -> str:
        """Run ALL checks, return compact context + actions."""
        compact: str = await SmartContextBuilder.build_compact(file_path)
        if not compact:
            return f"{file_path}: all checks passed"
        return compact

    @staticmethod
    async def smart_context_actions(file_path: str) -> str:
        """Run ALL checks, return compact context + suggested actions."""
        compact, actions = await SmartContextBuilder.build_with_actions(file_path)
        parts: list[str] = []
        if compact:
            parts.append(compact)
        if actions:
            parts.append("Suggested actions:")
            for action in actions:
                parts.append(f"  - {action}")
        if not parts:
            return f"{file_path}: all checks passed"
        return "\n".join(parts)

    @staticmethod
    async def run_tests(target: str, expression: str | None = None) -> str:
        """Run tests on a file or directory. Auto-discovers tests if target is a file."""
        from pathlib import Path as _P

        p = _P(target)
        if p.is_file() and not target.startswith("test"):
            # Auto-discover tests for this file.
            return await SmartContextBuilder.run_tests(target)
        return await TestRunner.run(target, expression)

    @staticmethod
    @mcp_cache(ttl=5.0)
    def profile_file(file_path: str) -> str:
        """Full AST-based performance profile of a file."""
        profile = PerformanceAnalyzer.analyze(file_path)
        return profile.to_compact()

    @staticmethod
    @mcp_cache(ttl=5.0)
    def profile_file_actions(file_path: str) -> str:
        """Performance profile + suggested actions."""
        profile = PerformanceAnalyzer.analyze(file_path)
        parts: list[str] = [profile.to_compact()]
        actions: list[str] = profile.to_actions()
        if actions:
            parts.append("Optimizations:")
            for a in actions:
                parts.append(f"  → {a}")
        return "\n".join(parts)

    @staticmethod
    @mcp_cache(ttl=5.0)
    def import_weights(file_path: str) -> str:
        """Import weight analysis sorted by heaviest."""
        weights = PerformanceAnalyzer.import_weights(file_path)
        if not weights:
            return f"{file_path}: no imports"
        lines: list[str] = [f"{file_path}: {len(weights)} imports"]
        for w in weights:
            origin: str = "stdlib" if w.is_stdlib else "THIRD-PARTY"
            lines.append(f"  {w.module} ({origin}) ~{format_bytes(w.estimated_weight)}")
        return "\n".join(lines)

    @staticmethod
    @mcp_cache(ttl=5.0)
    def function_weights(file_path: str) -> str:
        """Function weight analysis sorted by complexity."""
        weights = PerformanceAnalyzer.function_weights(file_path)
        if not weights:
            return f"{file_path}: no functions"
        lines: list[str] = [f"{file_path}: {len(weights)} functions"]
        for w in weights:
            lines.append(f"  {w}")
        return "\n".join(lines)

    @staticmethod
    @mcp_cache(ttl=5.0)
    def file_weight(file_path: str) -> str:
        """Complete weight breakdown for a file."""
        info = PerformanceAnalyzer.file_weight(file_path)
        lines: list[str] = [
            f"{info['file']}:",
            f"  size: {info['size_human']} ({info['lines']} lines)",
            f"  imports: {info['imports']} ({info['third_party']} third-party)",
            f"  import weight: {info['import_weight']}",
            f"  functions: {info['functions']}, classes: {info['classes']}",
            f"  global vars: {info['global_vars']}",
            f"  max nesting: {info['max_depth']}",
            f"  total complexity: {info['total_cc']}",
        ]
        return "\n".join(lines)

    @staticmethod
    def get_timing(name: str | None = None) -> str:
        """Get timing stats from @timed decorators."""
        stats = get_timing_stats(name)
        if not stats:
            return "No timing data collected"
        lines: list[str] = [f"{len(stats)} timing record(s):"]
        for s in stats[:20]:
            lines.append(f"  {s}")
        return "\n".join(lines)

    @staticmethod
    def get_memory_stats(name: str | None = None) -> str:
        """Get memory stats from @track_memory decorators."""
        stats = get_memory_stats(name)
        if not stats:
            return "No memory data collected"
        lines: list[str] = [f"{len(stats)} memory record(s):"]
        for s in stats[:20]:
            lines.append(f"  {s}")
        return "\n".join(lines)

    @staticmethod
    def clear_profiler_stats() -> str:
        """Clear all collected profiling data."""
        clear_stats()
        return "Profiler stats cleared"

    @staticmethod
    def object_weight(obj_repr: str) -> str:
        """Estimate memory weight of a Python literal expression."""
        try:
            import ast as _ast

            tree = _ast.parse(obj_repr, mode="eval")
            # Only support literals.
            if not isinstance(
                tree.body,
                (
                    _ast.Constant,
                    _ast.List,
                    _ast.Dict,
                    _ast.Set,
                    _ast.Tuple,
                ),
            ):
                return (
                    "Only literal expressions supported "
                    "(str, int, list, dict, set, tuple)"
                )
            obj = _ast.literal_eval(tree.body)
            w: int = object_weight(obj)
            return f"{obj_repr}: ~{format_bytes(w)}"
        except (ValueError, SyntaxError, TypeError) as exc:
            return f"Error: {exc}"

    @staticmethod
    def run_and_capture(file_path: str) -> str:
        """Execute a Python file and capture all runtime errors."""
        return FileRunner.run(file_path)

    @staticmethod
    def test_function(
        file_path: str,
        function_name: str,
        args: list[str] | None = None,
        kwargs: dict[str, str] | None = None,
    ) -> str:
        """Execute a specific function and return result."""
        return FileRunner.run_function(file_path, function_name, args, kwargs)

    @staticmethod
    def check_syntax_with_context(file_path: str) -> str:
        """Check syntax with source context on error."""
        return FileRunner.check_syntax(file_path)

    @staticmethod
    def check_types_runtime(file_path: str) -> str:
        """Run file and capture type-related runtime errors."""
        profile: RuntimeProfile = RuntimeExecutor.execute_file(file_path)
        type_errors: list[str] = []
        for e in profile.errors:
            if e.error_type in ("TypeError", "AttributeError", "NameError"):
                type_errors.append(e.to_compact())
        if not type_errors:
            return f"{file_path}: no type errors at runtime"
        return "\n".join(type_errors)


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="lint_and_fix",
            description=(
                "Run linters + auto-fix (codemods + ruff + black) in one call."
                " Returns lint report + residue. Best single tool for file analysis."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                    "linters": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific linters (default: all)",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="lint_file",
            description="Run all linters on a Python file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                    "linters": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific linters",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="fix_file",
            description=(
                "Deterministic auto-fix (codemods + ruff --fix --unsafe-fixes"
                " + black), then return ONLY the residue that needs judgment."
                " Run BEFORE hand-editing to save tokens."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="check_syntax",
            description="Quick syntax check.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="lint_batch",
            description="Lint multiple files at once.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of file paths",
                    },
                },
                "required": ["file_paths"],
            },
        ),
        Tool(
            name="get_skills",
            description="Detect skills + get rules for a file in one call.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="validate_file",
            description="Validate file against python-pro rules.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="validate_batch",
            description="Validate multiple files against python-pro rules.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of file paths",
                    },
                },
                "required": ["file_paths"],
            },
        ),
        Tool(
            name="analyze_types",
            description="Analyze types in a Python file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="generate_docstrings",
            description="Generate docstrings with type info for a file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="check_annotations",
            description="Report variables missing type annotations (no writes).",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="get_patterns",
            description="List frequent linter error patterns learned over time.",
            inputSchema={
                "type": "object",
                "properties": {
                    "min_count": {
                        "type": "integer",
                        "description": "Minimum occurrences to include",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="run_tests",
            description=(
                "Run pytest on a file or directory. Auto-discovers tests for source files."
                " Optional -k expression for filtering."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "File or directory to test",
                    },
                    "expression": {
                        "type": "string",
                        "description": "Optional -k expression",
                    },
                },
                "required": ["target"],
            },
        ),
        Tool(
            name="security_scan",
            description="Scan a file's AST for insecure patterns.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="complexity_report",
            description="Report cyclomatic complexity per function.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                    "max_complexity": {
                        "type": "integer",
                        "description": "Threshold to flag (default 10)",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="scaffold",
            description=(
                "Generate a conformant skeleton: module / service / "
                "fastapi_router / sqlalchemy_model / pydantic_model / pytest."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "description": (
                            "module|service|fastapi_router|"
                            "sqlalchemy_model|pydantic_model|pytest"
                        ),
                    },
                    "name": {
                        "type": "string",
                        "description": "Name for the generated artefact",
                    },
                },
                "required": ["kind", "name"],
            },
        ),
        Tool(
            name="fix_batch",
            description=(
                "Deterministic auto-fix of many files in parallel; returns only the "
                "per-file residue left after code-only fixes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of file paths",
                    },
                },
                "required": ["file_paths"],
            },
        ),
        Tool(
            name="summary",
            description=("Ultra-compact one-line status for a file (token-saver)."),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="outline",
            description=(
                "Compact signature-only map of a file or directory "
                "(token-saver; read structure without full files)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File or directory to outline",
                    },
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="check_stdlib",
            description=(
                "Flag third-party imports replaceable by stdlib or by a "
                "safer/faster async library."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="deps_of",
            description=("Files that file_path imports (outgoing dependencies)."),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="dependents_of",
            description=("Files that import file_path (incoming dependencies)."),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="graph_of",
            description=(
                "Dependency subgraph around a file (deps + dependents, depth-limited)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Traversal depth (default 1)",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="exports_of",
            description=(
                "Public names (classes, functions, constants) exported by a file."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="affected_by",
            description=("All files transitively affected if file_path changes."),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="graph_summary",
            description=("Ultra-compact one-line dependency summary for a file."),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="rebuild_graph",
            description=("Force rebuild of the dependency graph cache."),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="smart_context",
            description=(
                "Run ALL checks (lint, validate, security, complexity, graph,"
                " skills) and return ultra-compact context. Zero context waste."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="smart_context_actions",
            description=(
                "Run ALL checks and return compact context + suggested actions."
                " Tells the AI exactly what to fix and what files are affected."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="run_and_capture",
            description=(
                "Execute a Python file and capture all runtime errors with"
                " line numbers, variable values, and conditions."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="test_function",
            description=(
                "Execute a specific function with test arguments and"
                " return result or error with full context."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                    "function_name": {
                        "type": "string",
                        "description": "Function to call",
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Positional args (JSON strings)",
                    },
                    "kwargs": {
                        "type": "object",
                        "description": "Keyword args (JSON values)",
                    },
                },
                "required": ["file_path", "function_name"],
            },
        ),
        Tool(
            name="check_types_runtime",
            description=(
                "Run file and capture only type-related runtime errors"
                " (TypeError, AttributeError, NameError)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="refactor_suggestions",
            description=(
                "Auto-detect refactoring opportunities: if→match, isinstance→match,"
                " mutable defaults, try/except/pass→suppress, string concat in loop."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="optimization_stats",
            description=(
                "Show optimization stats: AST cache, MCP cache, file metrics,"
                " lazy imports, profiling state."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="profiling_enable",
            description="Enable memory profiling (starts tracemalloc).",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="profiling_disable",
            description="Disable memory profiling (stops tracemalloc).",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="profiling_snapshot",
            description="Take a memory snapshot if profiling is enabled.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="stale_files",
            description="List files that haven't been analyzed recently.",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_age": {
                        "type": "number",
                        "description": "Max age in seconds (default 60)",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="clear_optimization_caches",
            description="Clear all optimization caches (AST, MCP, metrics).",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="auto_refactor",
            description=(
                "Auto-refactor: apply codemods (remove unused imports, sort imports,"
                " add future annotations, add slots, replace bare except,"
                " modernize syntax). Returns diff."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "Preview changes without writing (default true)",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="dead_code",
            description=(
                "Find dead code: unused imports, functions, classes, variables"
                " using vulture + AST analysis."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="security_scan_bandit",
            description="Security scan using bandit (SAST).",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="sort_imports",
            description="Sort imports using isort.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "Preview without writing (default true)",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="format_black",
            description="Format code with black.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="pre_commit_fix",
            description=(
                "Run ALL auto-fixers (autoflake, isort, ruff, black, pyupgrade)"
                " BEFORE AI edits. Maximum token savings."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "Preview changes without writing (default true)",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="compact_prompt",
            description=(
                "Generate ultra-compact AI prompt from analysis results."
                " 80% fewer tokens."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="refactor_prompt",
            description="Generate compact refactor prompt from suggestions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="dead_code_prompt",
            description="Generate compact dead code prompt.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="get_instruction",
            description="Get compact instruction for a skill category.",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Skill category (async, typing, performance, etc.)",
                    },
                },
                "required": ["category"],
            },
        ),
        Tool(
            name="generate_code",
            description=(
                "Generate Python code from template: module, dataclass, pydantic,"
                " service, test, router, sqlalchemy, cli."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "description": "module|dataclass|pydantic|service|test|router|sqlalchemy|cli",
                    },
                    "name": {
                        "type": "string",
                        "description": "Name for generated code",
                    },
                    "fields": {
                        "type": "object",
                        "description": "Field definitions (name: type)",
                    },
                },
                "required": ["kind", "name"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(
    name: str,
    arguments: dict[str, object],
) -> list[TextContent]:
    """Handle MCP tool calls."""
    match name:
        case "lint_and_fix":
            file_path: str = str(arguments["file_path"])
            linters: list[str] | None = arguments.get("linters")  # type: ignore[assignment]
            text: str = await MCPTools.lint_and_fix(file_path, linters)
            return [TextContent(type="text", text=text)]

        case "lint_file":
            file_path = str(arguments["file_path"])
            linters = arguments.get("linters")  # type: ignore[assignment]
            text = await MCPTools.lint_file(file_path, linters)
            return [TextContent(type="text", text=text)]

        case "fix_file":
            file_path = str(arguments["file_path"])
            text = await MCPTools.fix_file(file_path)
            return [TextContent(type="text", text=text)]

        case "check_syntax":
            file_path = str(arguments["file_path"])
            text = MCPTools.check_syntax(file_path)
            return [TextContent(type="text", text=text)]

        case "lint_batch":
            file_paths: list[str] = MCPTools._str_list(arguments["file_paths"])
            text = await MCPTools.lint_batch(file_paths)
            return [TextContent(type="text", text=text)]

        case "get_skills":
            file_path = str(arguments["file_path"])
            # Get analysis from CodeAnalyzer.
            analysis: dict[str, object] = CodeAnalyzer.analyze(file_path)
            skills: list[str] = MCPTools._str_list(analysis["active_skills"])
            # Get rules from SkillDetector.
            detected = SkillDetector.detect(file_path)
            rules: str = SkillDetector.get_rules(detected)
            # Combine results.
            parts: list[str] = [
                f"File: {file_path}",
                f"Active skills: {', '.join(skills)}",
                f"Has async: {analysis['has_async']}",
                f"Has HTTP: {analysis['has_http']}",
                f"Has database: {analysis['has_database']}",
                f"Has patterns: {analysis['has_patterns']}",
            ]
            if rules:
                parts.append(f"\nRules:\n{rules}")
            text = "\n".join(parts)
            return [TextContent(type="text", text=text)]

        case "validate_file":
            file_path = str(arguments["file_path"])
            text = MCPTools.validate_file(file_path)
            return [TextContent(type="text", text=text)]

        case "validate_batch":
            file_paths = MCPTools._str_list(arguments["file_paths"])
            text = MCPTools.validate_batch(file_paths)
            return [TextContent(type="text", text=text)]

        case "analyze_types":
            file_path = str(arguments["file_path"])
            text = MCPTools.analyze_types(file_path)
            return [TextContent(type="text", text=text)]

        case "generate_docstrings":
            file_path = str(arguments["file_path"])
            text = MCPTools.generate_docstrings(file_path)
            return [TextContent(type="text", text=text)]

        case "check_annotations":
            file_path = str(arguments["file_path"])
            text = MCPTools.check_annotations(file_path)
            return [TextContent(type="text", text=text)]

        case "get_patterns":
            min_count: int = MCPTools._as_int(arguments.get("min_count", 1), 1)
            text = MCPTools.get_patterns(min_count)
            return [TextContent(type="text", text=text)]

        case "run_tests":
            target: str = str(arguments["target"])
            expression: str | None = arguments.get("expression")  # type: ignore[assignment]
            text = await MCPTools.run_tests(target, expression)
            return [TextContent(type="text", text=text)]

        case "security_scan":
            file_path = str(arguments["file_path"])
            text = SecurityScanner.scan(file_path)
            return [TextContent(type="text", text=text)]

        case "complexity_report":
            file_path = str(arguments["file_path"])
            max_complexity: int = MCPTools._as_int(
                arguments.get("max_complexity", 10),
                10,
            )
            text = ComplexityAnalyzer.report(file_path, max_complexity)
            return [TextContent(type="text", text=text)]

        case "scaffold":
            kind: str = str(arguments["kind"])
            scaffold_name: str = str(arguments["name"])
            text = Scaffolder.generate(kind, scaffold_name)
            return [TextContent(type="text", text=text)]

        case "fix_batch":
            file_paths = MCPTools._str_list(arguments["file_paths"])
            text = await MCPTools.fix_batch(file_paths)
            return [TextContent(type="text", text=text)]

        case "summary":
            file_path = str(arguments["file_path"])
            text = MCPTools.summary(file_path)
            return [TextContent(type="text", text=text)]

        case "outline":
            outline_path: str = str(arguments["path"])
            text = Outline.of(outline_path)
            return [TextContent(type="text", text=text)]

        case "check_stdlib":
            file_path = str(arguments["file_path"])
            text = StdlibFirstChecker.check(file_path)
            return [TextContent(type="text", text=text)]

        case "deps_of":
            file_path = str(arguments["file_path"])
            graph: CodeGraph = _get_graph()
            deps: list[str] = graph.deps_of(file_path)
            if deps:
                text = f"{file_path} imports:\n" + "\n".join(f"  {d}" for d in deps)
            else:
                text = f"{file_path}: no imports"
            return [TextContent(type="text", text=text)]

        case "dependents_of":
            file_path = str(arguments["file_path"])
            graph = _get_graph()
            rels: list[str] = graph.dependents_of(file_path)
            if rels:
                lines = [f"{file_path} is imported by:"]
                lines.extend(f"  {r}" for r in rels)
                text = "\n".join(lines)
            else:
                text = f"{file_path}: not imported by anything"
            return [TextContent(type="text", text=text)]

        case "graph_of":
            file_path = str(arguments["file_path"])
            depth: int = MCPTools._as_int(arguments.get("depth", 1), 1)
            graph = _get_graph()
            subgraph: dict[str, object] = graph.graph_of(file_path, depth)
            text = dumps(subgraph, indent=2, ensure_ascii=False)
            return [TextContent(type="text", text=text)]

        case "exports_of":
            file_path = str(arguments["file_path"])
            graph = _get_graph()
            exports: list[str] = graph.exports_of(file_path)
            if exports:
                text = f"{file_path} exports:\n" + "\n".join(f"  {e}" for e in exports)
            else:
                text = f"{file_path}: no public exports"
            return [TextContent(type="text", text=text)]

        case "affected_by":
            file_path = str(arguments["file_path"])
            graph = _get_graph()
            affected: list[str] = graph.affected_by(file_path)
            if affected:
                lines = [f"Changing {file_path} affects:"]
                lines.extend(f"  {a}" for a in affected)
                text = "\n".join(lines)
            else:
                text = f"{file_path}: nothing depends on it"
            return [TextContent(type="text", text=text)]

        case "graph_summary":
            file_path = str(arguments["file_path"])
            graph = _get_graph()
            text = graph.summary(file_path)
            return [TextContent(type="text", text=text)]

        case "rebuild_graph":
            global _graph
            _graph = CodeGraph()
            _graph.build()
            _graph.save()
            text = f"Graph rebuilt: {len(_graph.to_dict())} files indexed"
            return [TextContent(type="text", text=text)]

        case "smart_context":
            file_path = str(arguments["file_path"])
            text = await MCPTools.smart_context(file_path)
            return [TextContent(type="text", text=text)]

        case "smart_context_actions":
            file_path = str(arguments["file_path"])
            text = await MCPTools.smart_context_actions(file_path)
            return [TextContent(type="text", text=text)]

        case "run_and_capture":
            file_path = str(arguments["file_path"])
            text = MCPTools.run_and_capture(file_path)
            return [TextContent(type="text", text=text)]

        case "test_function":
            file_path = str(arguments["file_path"])
            func_name = str(arguments["function_name"])
            args = arguments.get("args")  # type: ignore[assignment]
            kwargs = arguments.get("kwargs")  # type: ignore[assignment]
            text = MCPTools.test_function(file_path, func_name, args, kwargs)
            return [TextContent(type="text", text=text)]

        case "check_types_runtime":
            file_path = str(arguments["file_path"])
            text = MCPTools.check_types_runtime(file_path)
            return [TextContent(type="text", text=text)]

        case "refactor_suggestions":
            file_path = str(arguments["file_path"])
            tree = parse_ast_cached(file_path)
            suggestions = detect_refactor_opportunities(file_path, tree)
            if not suggestions:
                text = f"{file_path}: no refactoring opportunities found"
            else:
                sorted_s = sorted(suggestions, key=lambda s: -s.confidence)
                lines = [f"{file_path}: {len(sorted_s)} suggestions"]
                for s in sorted_s[:10]:
                    lines.append(f"  {s.to_compact()}")
                text = "\n".join(lines)
            return [TextContent(type="text", text=text)]

        case "optimization_stats":
            ast_stats = ast_cache_stats()
            lazy_stats = lazy_import_stats()
            file_metrics = metrics_summary()
            profiling = profiling_is_enabled()
            lines = [
                "Optimization stats:",
                f"  AST cache: {ast_stats['entries']} entries (TTL {ast_stats['max_age_seconds']}s)",
                f"  Lazy imports: {lazy_stats['cached_imports']} cached",
                f"  File metrics: {file_metrics['files']} files, {file_metrics.get('total_lines', 0)} lines",
                f"  Stale files: {file_metrics.get('stale_files', 0)}",
                f"  Profiling: {'enabled' if profiling else 'disabled'}",
            ]
            text = "\n".join(lines)
            return [TextContent(type="text", text=text)]

        case "profiling_enable":
            profiling_enable()
            return [
                TextContent(type="text", text="Profiling enabled (tracemalloc started)")
            ]

        case "profiling_disable":
            profiling_disable()
            return [
                TextContent(
                    type="text", text="Profiling disabled (tracemalloc stopped)"
                )
            ]

        case "profiling_snapshot":
            snap = profiling_snapshot()
            if snap is None:
                text = "Profiling not enabled. Call profiling_enable first."
            else:
                text = (
                    f"Memory snapshot:\n"
                    f"  Current: {snap['current_human']}\n"
                    f"  Peak: {snap['peak_human']}"
                )
            return [TextContent(type="text", text=text)]

        case "stale_files":
            max_age = float(arguments.get("max_age", 60.0))
            stale = get_stale_files(max_age)
            if not stale:
                text = f"No files stale (>{max_age}s)"
            else:
                lines = [f"{len(stale)} stale files (>{max_age}s):"]
                for fp in stale[:20]:
                    lines.append(f"  {fp}")
                text = "\n".join(lines)
            return [TextContent(type="text", text=text)]

        case "clear_optimization_caches":
            mcp_count = mcp_cache_clear()
            text = (
                f"Caches cleared:\n"
                f"  MCP cache: {mcp_count} entries removed\n"
                f"  (AST cache expires automatically via TTL)"
            )
            return [TextContent(type="text", text=text)]

        case "auto_refactor":
            file_path = str(arguments["file_path"])
            dry_run = bool(arguments.get("dry_run", True))
            result = CodemodEngine.apply_all(file_path, dry_run=dry_run)
            if result.applied:
                text = f"{result.to_compact()}\n{result.to_diff()}"
            else:
                text = result.to_compact()
            return [TextContent(type="text", text=text)]

        case "dead_code":
            file_path = str(arguments["file_path"])
            result = DeadCodeAnalyzer.analyze(file_path)
            text = result.to_compact()
            return [TextContent(type="text", text=text)]

        case "security_scan_bandit":
            file_path = str(arguments["file_path"])
            result = SecurityScanner.scan(file_path)
            if result.total == 0:
                text = f"{file_path}: no security issues (bandit)"
            else:
                lines = [f"{file_path}: {result.total} finding(s)"]
                for f in result.findings[:10]:
                    lines.append(f"  {f}")
                text = "\n".join(lines)
            return [TextContent(type="text", text=text)]

        case "sort_imports":
            file_path = str(arguments["file_path"])
            dry_run = bool(arguments.get("dry_run", True))
            result = ImportSorter.sort(file_path, dry_run=dry_run)
            text = result.to_compact()
            if result.diff and not dry_run:
                text += f"\n{result.diff[:500]}"
            return [TextContent(type="text", text=text)]

        case "format_black":
            file_path = str(arguments["file_path"])
            result = CodeFormatter.format(file_path, dry_run=False)
            text = result.to_compact()
            return [TextContent(type="text", text=text)]

        case "pre_commit_fix":
            file_path = str(arguments["file_path"])
            dry_run = bool(arguments.get("dry_run", True))
            result = PreCommitFixer.fix_all(file_path, dry_run=dry_run)
            text = result.to_compact()
            if result.fixed:
                text += "\n" + result.to_diff_summary()
            if result.errors:
                text += "\n  errors: " + ", ".join(result.errors)
            return [TextContent(type="text", text=text)]

        case "compact_prompt":
            file_path = str(arguments["file_path"])
            ctx = await SmartContextBuilder.build(file_path)
            prompt = PromptBuilder.from_smart_context(ctx)
            text = prompt.to_tokens()
            return [TextContent(type="text", text=text)]

        case "refactor_prompt":
            file_path = str(arguments["file_path"])
            suggestions = detect_refactor_opportunities(file_path)
            prompt = RefactorPromptBuilder.from_suggestions(file_path, suggestions)
            text = prompt.to_tokens()
            return [TextContent(type="text", text=text)]

        case "dead_code_prompt":
            file_path = str(arguments["file_path"])
            result = DeadCodeAnalyzer.analyze(file_path)
            prompt = DeadCodePromptBuilder.from_result(result)
            text = prompt.to_tokens()
            return [TextContent(type="text", text=text)]

        case "get_instruction":
            category = str(arguments["category"])
            text = get_instruction(category)
            if not text:
                available = ", ".join(sorted(SKILL_INSTRUCTIONS.keys()))
                text = f"Unknown category. Available: {available}"
            return [TextContent(type="text", text=text)]

        case "generate_code":
            kind = str(arguments["kind"])
            gen_name = str(arguments["name"])
            fields = arguments.get("fields")  # type: ignore
            spec = {"kind": kind, "name": gen_name}
            if fields:
                spec["fields"] = fields
            generated = CodeGenEngine.from_spec(spec)
            text = f"[{generated.kind}] {generated.name}\n\n{generated.source}"
            return [TextContent(type="text", text=text)]

        case _:
            return [
                TextContent(
                    type="text",
                    text=f"Unknown tool: {name}",
                )
            ]


async def main() -> None:
    """Start MCP server on stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    run(main())
