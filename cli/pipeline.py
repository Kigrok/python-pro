#!/usr/bin/env python3
# cli/pipeline.py — One-call deterministic pass: fix everything, surface only residue.

from __future__ import annotations

from asyncio import gather, to_thread
from dataclasses import dataclass, field
from pathlib import Path

from cli.annotation_fixer import AnnotationReporter, MissingAnnotation
from cli.cache import SemanticCache
from cli.deps import DependencyFinding, StdlibFirstChecker
from cli.fixer import CodeFixer, FixOutcome
from cli.linters import run_linters
from cli.metrics import ComplexityAnalyzer, FunctionComplexity
from cli.models import FileReport, LinterResult, LintError
from cli.optimizations import parse_ast_cached
from cli.security import SecurityFinding, SecurityScanner
from cli.validator import PythonProValidator, ValidationIssue


@dataclass(slots=True)
class PipelineResult:
    """Outcome of one deterministic pass over a file, plus the residue."""

    file: str
    outcome: FixOutcome
    lint_errors: list[LintError] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)
    annotations: list[MissingAnnotation] = field(default_factory=list)
    security: list[SecurityFinding] = field(default_factory=list)
    complexity: list[FunctionComplexity] = field(default_factory=list)
    deps: list[DependencyFinding] = field(default_factory=list)

    @property
    def residual_count(self) -> int:
        """Issues left for a human/AI after every deterministic fix ran."""
        return (
            len(self.lint_errors)
            + len(self.issues)
            + len(self.annotations)
            + len(self.security)
            + len(self.complexity)
            + len(self.deps)
        )

    def residue_lines(self) -> list[str]:
        """Residual issues as compact lines, hard errors first."""
        errors: list[str] = [f"  {e.compact}" for e in self.lint_errors]
        errors += [
            f"  {self.file}:{f.line}: [security/{f.rule}] {f.message}"
            for f in self.security
        ]
        warns: list[str] = []
        issue: ValidationIssue
        for issue in self.issues:
            line: str = f"  {self.file}:{issue.line}: [{issue.rule}] {issue.message}"
            (errors if issue.severity == "error" else warns).append(line)
        warns += [
            f"  {self.file}:{c.line}: [complexity] {c.name}() CC={c.score}"
            for c in self.complexity
        ]
        warns += [
            f"  {self.file}:{d.line}: [{d.rule}] {d.module} -> {d.suggestion}"
            for d in self.deps
        ]
        ann: list[str] = [
            f"  {self.file}:{miss.line}: missing annotation '{miss.name}'"
            for miss in self.annotations
        ]
        return errors + warns + ann

    def summary(self, cap: int = 12) -> str:
        """Token-frugal report; '' when nothing needs the AI's attention."""
        if self.residual_count == 0:
            return ""
        name: str = Path(self.file).name
        body: list[str] = self.residue_lines()
        shown: list[str] = body[:cap]
        extra: int = len(body) - len(shown)
        if extra > 0:
            shown.append(f"  (+{extra} more)")
        head: str = (
            f"python-pro {name}: {self.residual_count} issue(s) remain after auto-fix"
        )
        return head + "\n" + "\n".join(shown)

    def one_line(self) -> str:
        """Ultra-compact one-line status for token savings."""
        if self.residual_count == 0:
            return f"{Path(self.file).name}: clean"
        counts: list[str] = []
        if self.lint_errors:
            counts.append(f"{len(self.lint_errors)} lint")
        if self.issues:
            counts.append(f"{len(self.issues)} rule")
        if self.security:
            counts.append(f"{len(self.security)} sec")
        if self.complexity:
            counts.append(f"{len(self.complexity)} cc")
        if self.deps:
            counts.append(f"{len(self.deps)} dep")
        if self.annotations:
            counts.append(f"{len(self.annotations)} ann")
        name: str = Path(self.file).name
        return f"{name}: {self.residual_count} issues ({', '.join(counts)})"


class DeterministicPipeline:
    """Fix a file with code only, then collect what code could not fix."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    async def run(
        file_path: str,
        lint: list[str] | None = None,
    ) -> PipelineResult:
        """Auto-fix, then lint/validate/annotate; return the residue."""
        # Semantic skip: a structurally-unchanged file last seen clean needs no work.
        cached_hash: str = SemanticCache.ast_hash(file_path)
        if SemanticCache.is_clean(file_path, cached_hash):
            return PipelineResult(file=file_path, outcome=FixOutcome())

        path: Path = Path(file_path)

        outcome: FixOutcome = await CodeFixer.auto_fix(file_path)

        # Parse AST once for all scanners that need it (cached for batch calls).
        tree = parse_ast_cached(file_path)
        if tree is None:
            return PipelineResult(file=file_path, outcome=FixOutcome())

        # Run independent scanners in parallel via asyncio.gather + to_thread.
        results_coro = run_linters(file_path, lint or ["ruff"])
        validate_coro = to_thread(
            PythonProValidator.validate,
            path,
            tree,
        )
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
        result: PipelineResult = PipelineResult(
            file=file_path,
            outcome=outcome,
            lint_errors=report.all_errors(),
            issues=list(validation.issues),
            annotations=annotations,
            security=security,
            complexity=complexity,
            deps=deps,
        )
        if result.residual_count == 0:
            SemanticCache.mark_clean(file_path, cached_hash)
        return result

    @staticmethod
    async def run_fast(file_path: str) -> PipelineResult:
        """Fast path for hooks: cache check + ruff lint only, no full pipeline."""
        cached_hash: str = SemanticCache.ast_hash(file_path)
        if SemanticCache.is_clean(file_path, cached_hash):
            return PipelineResult(file=file_path, outcome=FixOutcome())

        results: list[LinterResult] = await run_linters(file_path, ["ruff"])
        report: FileReport = FileReport(file=file_path, results=results)
        result: PipelineResult = PipelineResult(
            file=file_path,
            outcome=FixOutcome(),
            lint_errors=report.all_errors(),
        )
        if result.residual_count == 0:
            SemanticCache.mark_clean(file_path, cached_hash)
        return result

    @staticmethod
    async def run_batch(
        file_paths: list[str],
        lint: list[str] | None = None,
    ) -> list[PipelineResult]:
        """Run pipeline on multiple files in parallel with shared AST cache."""
        return list(
            await gather(*(DeterministicPipeline.run(fp, lint) for fp in file_paths))
        )

    @staticmethod
    async def run_batch_fast(file_paths: list[str]) -> list[PipelineResult]:
        """Fast batch: cache check + ruff lint only for multiple files."""
        return list(
            await gather(*(DeterministicPipeline.run_fast(fp) for fp in file_paths))
        )
