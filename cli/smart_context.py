#!/usr/bin/env python3
# cli/smart_context.py — Pre-compute everything an AI needs after a file edit.

from __future__ import annotations

from asyncio import gather, to_thread
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from cli.annotation_fixer import AnnotationReporter, MissingAnnotation
from cli.cache import SemanticCache
from cli.codegraph import CodeGraph
from cli.deps import DependencyFinding, StdlibFirstChecker
from cli.linters import run_linters
from cli.metrics import ComplexityAnalyzer, FunctionComplexity
from cli.models import FileReport, LintError
from cli.optimizations import (
    RefactorSuggestion,
    SectionDelta,
    compress_compact_output,
    compute_delta,
    detect_refactor_opportunities,
    parse_ast_cached,
    update_file_metrics,
)
from cli.security import SecurityFinding, SecurityScanner
from cli.validator import PythonProValidator, ValidationIssue

# Module-level cache for CodeGraph (avoids reloading JSON on every build).
_graph_cache: CodeGraph | None = None
_graph_cache_root: Path | None = None


def _get_graph(root: Path) -> CodeGraph:
    """Get cached CodeGraph or load from disk."""
    global _graph_cache, _graph_cache_root
    if _graph_cache is not None and _graph_cache_root == root:
        return _graph_cache
    _graph_cache = CodeGraph.load(root=root)
    _graph_cache_root = root
    return _graph_cache


@dataclass(slots=True)
class SmartContext:
    """Pre-computed context for a file edit — all checks done, compact output."""

    file: str
    clean: bool = True
    lint_errors: list[LintError] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)
    annotations: list[MissingAnnotation] = field(default_factory=list)
    security: list[SecurityFinding] = field(default_factory=list)
    complexity: list[FunctionComplexity] = field(default_factory=list)
    deps: list[DependencyFinding] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    affected: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    test_result: str = ""
    refactor_suggestions: list[RefactorSuggestion] = field(default_factory=list)
    delta: SectionDelta | None = None

    @property
    def total_issues(self) -> int:
        return (
            len(self.lint_errors)
            + len(self.issues)
            + len(self.annotations)
            + len(self.security)
            + len(self.complexity)
            + len(self.deps)
        )

    def to_compact(self) -> str:
        """Ultra-compact output: grouped by rule for token savings."""
        if self.clean and not self.test_result and not self.refactor_suggestions:
            return ""

        parts: list[str] = []

        # Status line.
        status: str = "OK" if self.clean else f"{self.total_issues} issues"
        parts.append(f"[{status}] {self.file}")

        # Compressed grouped output.
        compressed = compress_compact_output(
            self.lint_errors,
            self.issues,
            self.security,
            self.complexity,
        )
        if compressed:
            parts.append(compressed)

        # Missing annotations (count only).
        if self.annotations:
            parts.append(f"  ann: {len(self.annotations)} missing")

        # Dependencies.
        if self.deps:
            dep_list: str = ", ".join(d.module for d in self.deps[:3])
            parts.append(f"  dep: {dep_list}")

        # Graph context.
        if self.exports:
            parts.append(f"  exports: {', '.join(self.exports[:5])}")
        if self.affected:
            parts.append(f"  affects: {len(self.affected)} file(s)")

        # Skills.
        if self.skills:
            parts.append(f"  skills: {', '.join(self.skills)}")

        # Refactor suggestions (top 3, highest confidence first).
        if self.refactor_suggestions:
            sorted_refs = sorted(
                self.refactor_suggestions,
                key=lambda r: -r.confidence,
            )
            refs = "; ".join(r.to_compact() for r in sorted_refs[:3])
            parts.append(f"  refactor: {refs}")

        # Delta info (only when there are changes).
        if self.delta and self.delta.has_changes:
            parts.append(f"  delta: {self.delta.to_compact()}")

        # Test result.
        if self.test_result:
            parts.append(f"  tests: {self.test_result}")

        return "\n".join(parts)

    def to_actions(self) -> list[str]:
        """Suggested actions for the AI."""
        actions: list[str] = []
        if self.lint_errors:
            actions.append(f"Fix {len(self.lint_errors)} lint error(s)")
        if self.issues:
            error_rules: list[str] = [
                i.rule for i in self.issues if i.severity == "error"
            ]
            if error_rules:
                actions.append(f"Fix rule violations: {', '.join(error_rules[:3])}")
        if self.security:
            actions.append(f"Address {len(self.security)} security finding(s)")
        if self.complexity:
            actions.append(f"Refactor {len(self.complexity)} complex function(s)")
        if self.annotations:
            actions.append(f"Add {len(self.annotations)} missing annotation(s)")
        if self.affected:
            actions.append(
                f"Check {len(self.affected)} dependent file(s): "
                + ", ".join(Path(a).name for a in self.affected[:3])
            )
        if self.refactor_suggestions:
            top = sorted(self.refactor_suggestions, key=lambda r: -r.confidence)[:3]
            for s in top:
                actions.append(f"Refactor: {s.description}")
        return actions


class SmartContextBuilder:
    """Build SmartContext for a file — runs all checks in parallel."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    async def build(file_path: str) -> SmartContext:
        """Run all checks and build compact context."""
        ctx: SmartContext = SmartContext(file=file_path)

        # Fast path: cache hit.
        cached_hash: str = SemanticCache.ast_hash(file_path)
        if SemanticCache.is_clean(file_path, cached_hash):
            ctx.clean = True
            return ctx

        # Run fixer first.
        from cli.fixer import CodeFixer

        await CodeFixer.auto_fix(file_path)

        # Parse AST once (cached for batch calls).
        tree = parse_ast_cached(file_path)
        path: Path = Path(file_path)

        # Compute delta for incremental analysis.
        source = ""
        with suppress(OSError):
            source = path.read_text(encoding="utf-8", errors="replace")

        sections = {
            "source_hash": cached_hash,
            "size": str(len(source)),
            "lines": str(source.count("\n") + 1) if source else "0",
        }
        delta = compute_delta(file_path, sections)
        ctx.delta = delta

        # Fast path: if only metadata changed (no source change), skip deep analysis.
        if delta.unchanged and not delta.changed and not delta.added:
            ctx.clean = True
            return ctx

        # Run all scanners in parallel.
        results_coro = run_linters(file_path, ["ruff"])
        validate_coro = to_thread(PythonProValidator.validate, path, tree)
        annotate_coro = to_thread(AnnotationReporter.check_file, path, tree)
        security_coro = to_thread(SecurityScanner.findings, file_path, tree)
        complexity_coro = to_thread(
            ComplexityAnalyzer.over_threshold, file_path, 10, tree
        )
        deps_coro = to_thread(StdlibFirstChecker.findings, file_path, tree)

        results, validation, annotations, security, complexity, deps = await gather(
            results_coro,
            validate_coro,
            annotate_coro,
            security_coro,
            complexity_coro,
            deps_coro,
        )

        report: FileReport = FileReport(file=file_path, results=results)
        ctx.lint_errors = report.all_errors()
        ctx.issues = list(validation.issues)
        ctx.annotations = annotations
        ctx.security = security
        ctx.complexity = complexity
        ctx.deps = deps
        ctx.clean = ctx.total_issues == 0

        # Refactor suggestions (async to avoid blocking).
        ctx.refactor_suggestions = await to_thread(
            detect_refactor_opportunities,
            file_path,
            tree,
        )

        # Graph context (cached).
        try:
            graph: CodeGraph = _get_graph(path.parent.parent)
            ctx.exports = graph.exports_of(file_path)
            ctx.affected = graph.affected_by(file_path)
        except (OSError, ValueError):
            pass

        # Skills.
        from skills.detector import SkillDetector

        ctx.skills = SkillDetector.detect(file_path)

        # Update file metrics.
        if source:
            update_file_metrics(
                file_path,
                size_bytes=len(source.encode()),
                line_count=source.count("\n") + 1,
                issue_count=ctx.total_issues,
                analysis_hash=cached_hash,
            )

        # Mark clean if no issues.
        if ctx.clean:
            SemanticCache.mark_clean(file_path, cached_hash)

        return ctx

    @staticmethod
    async def build_compact(file_path: str) -> str:
        """Build context and return compact string."""
        ctx: SmartContext = await SmartContextBuilder.build(file_path)
        return ctx.to_compact()

    @staticmethod
    async def build_with_actions(file_path: str) -> tuple[str, list[str]]:
        """Build context and return (compact, actions)."""
        ctx: SmartContext = await SmartContextBuilder.build(file_path)
        return ctx.to_compact(), ctx.to_actions()

    @staticmethod
    async def run_tests(file_path: str) -> str:
        """Run pytest on a test file or find and run related tests."""
        from cli.runner import TestRunner

        path: Path = Path(file_path)

        # If it's a test file, run it directly.
        if path.name.startswith("test_") or path.name.endswith("_test.py"):
            return await TestRunner.run(str(path))

        # Otherwise, look for a matching test file.
        test_names: list[str] = [
            f"test_{path.stem}.py",
            f"{path.stem}_test.py",
        ]
        for name in test_names:
            test_file: Path = path.parent / name
            if test_file.exists():
                return await TestRunner.run(str(test_file))

        # Look in tests/ directory.
        tests_dir: Path = path.parent.parent / "tests"
        if tests_dir.exists():
            for test_file in tests_dir.rglob(f"test_{path.stem}.py"):
                return await TestRunner.run(str(test_file))

        return ""
