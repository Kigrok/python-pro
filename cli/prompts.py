#!/usr/bin/env python3
# cli/prompts.py — Compact AI prompts: minimal tokens, maximum actionability.

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

# Token-efficient status codes.
_STATUS: Final[dict[str, str]] = {
    "ok": "✓",
    "warn": "⚠",
    "error": "✗",
    "fix": "→",
    "skip": "⊘",
}


@dataclass(slots=True)
class CompactPrompt:
    """Ultra-compact prompt for AI — minimal tokens."""

    file: str
    status: str  # ok, warn, error
    issues: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)

    def to_tokens(self) -> str:
        """Token-efficient format: ~80% fewer tokens than verbose."""
        if self.status == "ok" and not self.refs:
            return f"✓ {Path(self.file).name}"

        parts = [f"{_STATUS.get(self.status, '?')} {Path(self.file).name}"]

        if self.issues:
            # Group by code for compression.
            from collections import Counter

            counts = Counter(self.issues)
            grouped = ", ".join(
                f"{code}x{n}" if n > 1 else code for code, n in counts.most_common(5)
            )
            parts.append(f"  {grouped}")

        if self.actions:
            parts.append(f"  → {'; '.join(self.actions[:3])}")

        if self.refs:
            parts.append(f"  ♻ {'; '.join(self.refs[:2])}")

        return "\n".join(parts)

    def to_action(self) -> str:
        """Single-line action format."""
        if self.status == "ok":
            return f"clean: {self.file}"
        issues_str = ",".join(self.issues[:5])
        actions_str = ",".join(self.actions[:3])
        return f"{issues_str} → {actions_str}"


@dataclass(slots=True)
class PromptBatch:
    """Batch of compact prompts — optimized for bulk AI processing."""

    prompts: list[CompactPrompt] = field(default_factory=list)

    def to_tokens(self) -> str:
        """Token-efficient batch format."""
        if not self.prompts:
            return "all clean"

        lines = []
        for p in self.prompts:
            lines.append(p.to_tokens())

        # Add summary.
        total_issues = sum(len(p.issues) for p in self.prompts)
        total_actions = sum(len(p.actions) for p in self.prompts)
        if total_issues > 0:
            lines.append(f"Σ {total_issues} issues, {total_actions} actions")

        return "\n".join(lines)

    def to_ai_context(self) -> str:
        """Format for AI context — ready to paste."""
        parts = ["## python-pro status\n"]
        for p in self.prompts:
            parts.append(p.to_tokens())
        return "\n".join(parts)


class PromptBuilder:
    """Build compact prompts from analysis results."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def from_smart_context(ctx: object) -> CompactPrompt:
        """Build compact prompt from SmartContext."""
        file = getattr(ctx, "file", "unknown")
        issues: list[str] = []
        actions: list[str] = []

        lint_errors = getattr(ctx, "lint_errors", [])
        if lint_errors:
            from collections import Counter

            codes = Counter(getattr(e, "code", "?") for e in lint_errors)
            issues.extend(f"lint:{c}" for c, _ in codes.most_common(3))

        rule_issues = getattr(ctx, "issues", [])
        if rule_issues:
            from collections import Counter

            rules = Counter(getattr(i, "rule", "?") for i in rule_issues)
            issues.extend(f"rule:{r}" for r, _ in rules.most_common(3))

        security = getattr(ctx, "security", [])
        if security:
            issues.append(f"sec:{len(security)}")

        complexity = getattr(ctx, "complexity", [])
        if complexity:
            issues.append(f"cc:{len(complexity)}")

        annotations = getattr(ctx, "annotations", [])
        if annotations:
            issues.append(f"ann:{len(annotations)}")

        # Build actions.
        if lint_errors:
            actions.append(f"fix {len(lint_errors)} lint")
        if rule_issues:
            error_rules = [
                i for i in rule_issues if getattr(i, "severity", "") == "error"
            ]
            if error_rules:
                actions.append(f"fix {len(error_rules)} rules")
        if security:
            actions.append(f"fix {len(security)} sec")
        if complexity:
            actions.append(f"refactor {len(complexity)} cc")
        if annotations:
            actions.append(f"add {len(annotations)} ann")

        status = "ok" if not issues else ("warn" if not actions else "error")

        return CompactPrompt(
            file=file,
            status=status,
            issues=issues,
            actions=actions,
        )

    @staticmethod
    def from_pipeline_result(result: object) -> CompactPrompt:
        """Build compact prompt from PipelineResult."""
        file = getattr(result, "file", "unknown")
        issues: list[str] = []
        actions: list[str] = []

        lint_errors = getattr(result, "lint_errors", [])
        if lint_errors:
            issues.append(f"lint:{len(lint_errors)}")
            actions.append(f"fix {len(lint_errors)} lint")

        rule_issues = getattr(result, "issues", [])
        if rule_issues:
            issues.append(f"rule:{len(rule_issues)}")
            actions.append(f"fix {len(rule_issues)} rules")

        security = getattr(result, "security", [])
        if security:
            issues.append(f"sec:{len(security)}")
            actions.append(f"fix {len(security)} sec")

        complexity = getattr(result, "complexity", [])
        if complexity:
            issues.append(f"cc:{len(complexity)}")
            actions.append(f"refactor {len(complexity)} cc")

        annotations = getattr(result, "annotations", [])
        if annotations:
            issues.append(f"ann:{len(annotations)}")
            actions.append(f"add {len(annotations)} ann")

        deps = getattr(result, "deps", [])
        if deps:
            issues.append(f"dep:{len(deps)}")

        status = "ok" if not issues else "error"

        return CompactPrompt(
            file=file,
            status=status,
            issues=issues,
            actions=actions,
        )

    @staticmethod
    def batch(results: list[object]) -> PromptBatch:
        """Build batch prompt from multiple results."""
        prompts = []
        for r in results:
            if hasattr(r, "lint_errors"):
                prompts.append(PromptBuilder.from_pipeline_result(r))
            elif hasattr(r, "skills"):
                prompts.append(PromptBuilder.from_smart_context(r))
        return PromptBatch(prompts=prompts)


@dataclass(slots=True)
class RefactorPrompt:
    """Prompt for refactoring suggestions — ultra-compact."""

    file: str
    suggestions: list[str] = field(default_factory=list)
    confidence: list[float] = field(default_factory=list)

    def to_tokens(self) -> str:
        if not self.suggestions:
            return f"♻ {Path(self.file).name}: no refactoring needed"

        lines = [f"♻ {Path(self.file).name}:"]
        for s, c in zip(self.suggestions[:5], self.confidence[:5], strict=False):
            icon = "●" if c > 0.8 else "○"
            lines.append(f"  {icon} {s}")
        return "\n".join(lines)


class RefactorPromptBuilder:
    """Build refactor prompts from suggestions."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def from_suggestions(
        file_path: str,
        suggestions: list[object],
    ) -> RefactorPrompt:
        """Build refactor prompt from RefactorSuggestion list."""
        sorted_s = sorted(suggestions, key=lambda s: -getattr(s, "confidence", 0))
        return RefactorPrompt(
            file=file_path,
            suggestions=[s.to_compact() for s in sorted_s[:5]],
            confidence=[getattr(s, "confidence", 0) for s in sorted_s[:5]],
        )


@dataclass(slots=True)
class DeadCodePrompt:
    """Prompt for dead code — ultra-compact."""

    file: str
    imports: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)

    def to_tokens(self) -> str:
        total = (
            len(self.imports)
            + len(self.functions)
            + len(self.classes)
            + len(self.variables)
        )
        if total == 0:
            return f"⊘ {Path(self.file).name}: no dead code"

        parts = [f"⊘ {Path(self.file).name}: {total} dead"]
        if self.imports:
            parts.append(f"  imports: {', '.join(self.imports[:5])}")
        if self.functions:
            parts.append(f"  funcs: {', '.join(self.functions[:5])}")
        if self.classes:
            parts.append(f"  classes: {', '.join(self.classes[:5])}")
        if self.variables:
            parts.append(f"  vars: {', '.join(self.variables[:5])}")
        return "\n".join(parts)


class DeadCodePromptBuilder:
    """Build dead code prompts."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def from_result(result: object) -> DeadCodePrompt:
        """Build prompt from DeadCodeResult."""
        return DeadCodePrompt(
            file=getattr(result, "file", "unknown"),
            imports=getattr(result, "unused_imports", []),
            functions=getattr(result, "unused_functions", []),
            classes=getattr(result, "unused_classes", []),
            variables=getattr(result, "unused_variables", []),
        )


# Predefined instruction snippets — reusable, token-efficient.
INSTRUCTIONS: Final[dict[str, str]] = {
    "lint_fix": "fix lint errors",
    "rule_fix": "fix rule violations",
    "security_fix": "address security findings",
    "complexity_refactor": "refactor complex functions",
    "annotations_add": "add missing type annotations",
    "dead_code_remove": "remove dead code",
    "import_sort": "sort imports",
    "format": "format with black",
    "slots_add": "add __slots__ to classes",
    "modernize": "modernize syntax",
    "suppress": "replace try/except/pass with suppress",
    "match_case": "replace if/elif chain with match/case",
}

# Skill-specific compact instructions.
SKILL_INSTRUCTIONS: Final[dict[str, str]] = {
    "async": "use asyncio.gather, Semaphore, TaskGroup",
    "data_structures": "prefer deque, Counter, defaultdict",
    "typing": "strict types, no Any/Optional, use X | None",
    "performance": "lazy imports, cachetools, slots",
    "memory": "__slots__, generators, sys.getsizeof",
    "http": "aiohttp over requests, async by default",
    "database": "asyncpg over psycopg2, pool connections",
    "security": "no eval/exec, no shell=True, secrets module",
    "errors": "specific exceptions, chain with from, contextlib.suppress",
    "testing": "pytest fixtures, parametrize, mock",
    "logging": "structlog, JSON output, no print()",
    "config": "pydantic-settings, env vars, 12-factor",
    "cli": "typer over argparse, rich for output",
    "csv": "csv.DictReader, no pandas for simple tasks",
    "json": "orjson over json, msgspec for validation",
    "paths": "pathlib over os.path, Path.glob()",
    "strings": "str.join() over +=, f-strings",
    "collections": "Counter, defaultdict, deque, namedtuple",
    "itertools": "chain, islice, groupby over manual loops",
    "contextlib": "suppress, contextmanager, ExitStack",
    "functools": "lru_cache, partial, reduce",
    "operator": "itemgetter, attrgetter over lambdas",
    "heapq": "nlargest, nsmallest over sort+slice",
    "bisect": "insort, bisect_left over manual search",
    "enum": "Enum, IntEnum, Flag over constants",
    "dataclasses": "@dataclass(slots=True), field()",
    "abc": "ABC, abstractmethod for interfaces",
    "typing_extensions": "TypeAlias, ParamSpec for 3.11+",
    "cpython_patterns": "CPython stdlib patterns",
    "error_handling": "exception hierarchy, chaining, cleanup",
    "concurrency": "TaskGroup, Semaphore, async generators",
    "api_design": "protocols, singledispatch, overloads",
}


def get_instruction(category: str) -> str:
    """Get compact instruction for a category."""
    return SKILL_INSTRUCTIONS.get(category, INSTRUCTIONS.get(category, ""))
