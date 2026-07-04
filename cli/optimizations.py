#!/usr/bin/env python3
# cli/optimizations.py — All performance optimizations in one module.

from __future__ import annotations

import ast
import hashlib
import time
from collections import OrderedDict, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Final, TypeVar

F = TypeVar("F", bound=Callable[..., object])

# =============================================================================
# 1. Delta-incrementality — section-level caching
# =============================================================================

_SECTION_HASHES: Final[dict[str, dict[str, str]]] = {}


@dataclass(slots=True)
class SectionDelta:
    """Delta between two analysis runs — only changed sections."""

    changed: list[str]
    unchanged: list[str]
    added: list[str]
    removed: list[str]

    @property
    def has_changes(self) -> bool:
        return bool(self.changed or self.added or self.removed)

    def to_compact(self) -> str:
        parts: list[str] = []
        if self.changed:
            parts.append(f"changed: {', '.join(self.changed)}")
        if self.added:
            parts.append(f"added: {', '.join(self.added)}")
        if self.removed:
            parts.append(f"removed: {', '.join(self.removed)}")
        return "; ".join(parts) if parts else "no changes"


def _section_hash(file_path: str, section: str, content: str) -> str:
    """Hash a specific section of a file's analysis."""
    return hashlib.blake2b(content.encode(), digest_size=8).hexdigest()


def compute_delta(
    file_path: str,
    sections: dict[str, str],
) -> SectionDelta:
    """Compare current sections with cached hashes, return delta."""
    prev = _SECTION_HASHES.get(file_path, {})
    changed: list[str] = []
    added: list[str] = []
    removed: list[str] = []

    for name, content in sections.items():
        new_hash = _section_hash(file_path, name, content)
        if name in prev:
            if prev[name] != new_hash:
                changed.append(name)
        else:
            added.append(name)
        prev[name] = new_hash

    for name in prev:
        if name not in sections:
            removed.append(name)

    _SECTION_HASHES[file_path] = prev
    return SectionDelta(
        changed=changed,
        unchanged=[n for n in sections if n not in changed and n not in added],
        added=added,
        removed=removed,
    )


# =============================================================================
# 2. MCP call caching — LRU cache by (file_path, content_hash) with TTL
# =============================================================================

_MCP_CACHE: Final[OrderedDict[str, tuple[float, object]]] = OrderedDict()
_MCP_TTL: Final[float] = 5.0  # seconds
_MCP_MAX: Final[int] = 200


def mcp_cache(ttl: float = _MCP_TTL):
    """Decorator: cache MCP tool results by arguments with TTL + LRU eviction."""

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: object, **kwargs: object) -> object:
            if not kwargs:
                cache_key = f"{func.__name__}:{args}"
            else:
                sorted_kw = tuple(sorted(kwargs.items()))
                cache_key = f"{func.__name__}:{args}:{sorted_kw}"

            now = time.monotonic()
            if cache_key in _MCP_CACHE:
                cached_time, cached_val = _MCP_CACHE[cache_key]
                if now - cached_time < ttl:
                    _MCP_CACHE.move_to_end(cache_key)
                    return cached_val

            result = func(*args, **kwargs)
            _MCP_CACHE[cache_key] = (now, result)
            _MCP_CACHE.move_to_end(cache_key)

            # LRU eviction: only remove the oldest entry when over limit.
            while len(_MCP_CACHE) > _MCP_MAX:
                _MCP_CACHE.popitem(last=False)

            return result

        return wrapper  # type: ignore[return-value]

    return decorator


def mcp_cache_clear() -> int:
    """Clear MCP cache. Returns count removed."""
    count = len(_MCP_CACHE)
    _MCP_CACHE.clear()
    return count


# =============================================================================
# 3. Batch processing — shared AST parsing with mtime check
# =============================================================================

_AST_CACHE: Final[dict[str, tuple[float, float, ast.Module]]] = (
    {}
)  # path -> (mtime, cache_time, tree)
_AST_TTL: Final[float] = 30.0


def parse_ast_cached(file_path: str) -> ast.Module | None:
    """Parse AST with mtime-aware cache to skip unchanged files."""
    now = time.monotonic()
    try:
        stat = Path(file_path).stat()
        mtime = stat.st_mtime
    except OSError:
        return None

    if file_path in _AST_CACHE:
        cached_mtime, cached_time, tree = _AST_CACHE[file_path]
        # Skip if file hasn't changed and cache is fresh.
        if mtime == cached_mtime and now - cached_time < _AST_TTL:
            return tree

    try:
        source = Path(file_path).read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=file_path)
        _AST_CACHE[file_path] = (mtime, now, tree)
        return tree
    except (OSError, SyntaxError):
        return None


def batch_parse(file_paths: list[str]) -> dict[str, ast.Module | None]:
    """Parse multiple files, reusing cached ASTs."""
    result: dict[str, ast.Module | None] = {}
    for fp in file_paths:
        result[fp] = parse_ast_cached(fp)
    return result


def ast_cache_stats() -> dict[str, int]:
    """Stats for AST cache."""
    return {
        "entries": len(_AST_CACHE),
        "max_age_seconds": int(_AST_TTL),
    }


# =============================================================================
# 4. Lazy loading — importlib for rarely-used modules
# =============================================================================

_LAZY_IMPORTS: Final[dict[str, object]] = {}


def lazy_import(module_path: str, attr: str | None = None) -> object:
    """Import a module or attribute lazily, cache the result."""
    cache_key = f"{module_path}:{attr}" if attr else module_path
    if cache_key in _LAZY_IMPORTS:
        return _LAZY_IMPORTS[cache_key]

    import importlib

    mod = importlib.import_module(module_path)
    result = getattr(mod, attr) if attr else mod
    _LAZY_IMPORTS[cache_key] = result
    return result


def lazy_import_stats() -> dict[str, int]:
    """Stats for lazy imports."""
    return {"cached_imports": len(_LAZY_IMPORTS)}


# =============================================================================
# 5. Optional profiling — tracemalloc only on demand
# =============================================================================

_PROFILING_ENABLED: bool = False
_TRACEMALLOC_STARTED: bool = False


def profiling_enable() -> None:
    """Enable profiling mode — starts tracemalloc."""
    global _PROFILING_ENABLED, _TRACEMALLOC_STARTED
    _PROFILING_ENABLED = True
    if not _TRACEMALLOC_STARTED:
        import tracemalloc

        tracemalloc.start()
        _TRACEMALLOC_STARTED = True


def profiling_disable() -> None:
    """Disable profiling mode — stops tracemalloc."""
    global _PROFILING_ENABLED, _TRACEMALLOC_STARTED
    _PROFILING_ENABLED = False
    if _TRACEMALLOC_STARTED:
        import tracemalloc

        tracemalloc.stop()
        _TRACEMALLOC_STARTED = False


def profiling_is_enabled() -> bool:
    """Check if profiling is enabled."""
    return _PROFILING_ENABLED


def profiling_snapshot() -> dict[str, object] | None:
    """Take a memory snapshot if profiling is enabled."""
    if not _PROFILING_ENABLED:
        return None
    import tracemalloc

    current, peak = tracemalloc.get_traced_memory()
    return {
        "current_bytes": current,
        "peak_bytes": peak,
        "current_human": _format_bytes_fast(current),
        "peak_human": _format_bytes_fast(peak),
    }


def _format_bytes_fast(n: int) -> str:
    """Fast byte formatting without importing profiler."""
    if n < 1024:
        return f"{n}B"
    if n < 1048576:
        return f"{n / 1024:.1f}KB"
    return f"{n / 1048576:.1f}MB"


# =============================================================================
# 6. Streaming output — priority-ordered compact context
# =============================================================================


@dataclass(slots=True)
class StreamingChunk:
    """A chunk of output with priority for streaming."""

    priority: int  # 0=critical, 1=warning, 2=info, 3=detail
    content: str
    tokens_estimate: int

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, StreamingChunk):
            return NotImplemented
        return self.priority < other.priority


def priority_sort_chunks(chunks: list[StreamingChunk]) -> list[StreamingChunk]:
    """Sort chunks by priority (critical first)."""
    return sorted(chunks)


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(1, len(text) // 4)


# =============================================================================
# 7. Real-time metrics — file watcher state
# =============================================================================


@dataclass(slots=True)
class FileMetrics:
    """Real-time metrics for a file."""

    path: str
    last_modified: float
    last_analyzed: float
    size_bytes: int
    line_count: int
    issue_count: int = 0
    analysis_hash: str = ""

    @property
    def staleness(self) -> float:
        """Seconds since last analysis."""
        return time.monotonic() - self.last_analyzed


_FILE_METRICS: Final[dict[str, FileMetrics]] = {}


def update_file_metrics(
    file_path: str,
    size_bytes: int,
    line_count: int,
    issue_count: int = 0,
    analysis_hash: str = "",
) -> FileMetrics:
    """Update metrics for a file."""
    now = time.monotonic()
    metrics = FileMetrics(
        path=file_path,
        last_modified=now,
        last_analyzed=now,
        size_bytes=size_bytes,
        line_count=line_count,
        issue_count=issue_count,
        analysis_hash=analysis_hash,
    )
    _FILE_METRICS[file_path] = metrics
    return metrics


def get_file_metrics(file_path: str) -> FileMetrics | None:
    """Get metrics for a file."""
    return _FILE_METRICS.get(file_path)


def get_stale_files(max_age: float = 60.0) -> list[str]:
    """Get files that haven't been analyzed recently."""
    now = time.monotonic()
    return [fp for fp, m in _FILE_METRICS.items() if now - m.last_analyzed > max_age]


def metrics_summary() -> dict[str, object]:
    """Summary of all file metrics."""
    if not _FILE_METRICS:
        return {"files": 0}
    total_lines = sum(m.line_count for m in _FILE_METRICS.values())
    total_issues = sum(m.issue_count for m in _FILE_METRICS.values())
    stale = get_stale_files()
    return {
        "files": len(_FILE_METRICS),
        "total_lines": total_lines,
        "total_issues": total_issues,
        "stale_files": len(stale),
    }


# =============================================================================
# 8. Auto-refactor suggestions — AST pattern matching
# =============================================================================


@dataclass(slots=True)
class RefactorSuggestion:
    """An auto-detected refactoring opportunity."""

    file: str
    line: int
    pattern: str
    description: str
    before: str
    after: str
    confidence: float  # 0.0 to 1.0

    def to_compact(self) -> str:
        return f"[{self.pattern}] L{self.line}: {self.description}"


def _is_dataclass_decorator(decorator: ast.expr) -> bool:
    """True if a decorator is `dataclass` or `dataclass(...)`."""
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    if isinstance(target, ast.Name):
        return target.id == "dataclass"
    if isinstance(target, ast.Attribute):
        return target.attr == "dataclass"
    return False


def detect_refactor_opportunities(
    file_path: str,
    tree: ast.Module | None = None,
) -> list[RefactorSuggestion]:
    """Scan AST for common refactoring patterns."""
    if tree is None:
        tree = parse_ast_cached(file_path)
    if tree is None:
        return []

    suggestions: list[RefactorSuggestion] = []
    source_lines: list[str] = []
    try:
        source_lines = (
            Path(file_path)
            .read_text(
                encoding="utf-8",
                errors="replace",
            )
            .splitlines()
        )
    except OSError:
        return suggestions

    for node in ast.walk(tree):
        # Pattern 1: if/elif/elif chain → match/case
        if isinstance(node, ast.If):
            chain_len = _count_elif_chain(node)
            if chain_len >= 3:
                src = (
                    source_lines[node.lineno - 1]
                    if node.lineno <= len(source_lines)
                    else ""
                )
                suggestions.append(
                    RefactorSuggestion(
                        file=file_path,
                        line=node.lineno,
                        pattern="if_to_match",
                        description=f"if/elif chain ({chain_len} branches) → match/case",
                        before=src.strip(),
                        after="match value:\n    case ...: ...",
                        confidence=0.8,
                    )
                )

        # Pattern 2: isinstance(x, (A, B)) → match/case
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "isinstance"
            and len(node.args) > 1
        ):
            second = node.args[1]
            if isinstance(second, ast.Tuple) and len(second.elts) > 3:
                src = (
                    source_lines[node.lineno - 1]
                    if node.lineno <= len(source_lines)
                    else ""
                )
                suggestions.append(
                    RefactorSuggestion(
                        file=file_path,
                        line=node.lineno,
                        pattern="isinstance_to_match",
                        description=f"isinstance with {len(second.elts)} types → match/case",
                        before=src.strip(),
                        after="match value:\n    case TypeA: ...\n    case TypeB: ...",
                        confidence=0.7,
                    )
                )

        # Pattern 3: mutable default argument
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults + node.args.kw_defaults:
                if default and isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    src = (
                        source_lines[node.lineno - 1]
                        if node.lineno <= len(source_lines)
                        else ""
                    )
                    suggestions.append(
                        RefactorSuggestion(
                            file=file_path,
                            line=node.lineno,
                            pattern="mutable_default",
                            description=f"Mutable default in {node.name}() → use None + factory",
                            before=src.strip(),
                            after=f"def {node.name}(..., items=None):\n    items = items or []",
                            confidence=0.95,
                        )
                    )

        # Pattern 4: try/except/pass → contextlib.suppress
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                if (
                    (
                        handler.type is None
                        or (
                            isinstance(handler.type, ast.Name)
                            and handler.type.id == "Exception"
                        )
                    )
                    and len(handler.body) == 1
                    and isinstance(handler.body[0], ast.Pass)
                ):
                    src = (
                        source_lines[node.lineno - 1]
                        if node.lineno <= len(source_lines)
                        else ""
                    )
                    exc_name = ""
                    if handler.type and isinstance(handler.type, ast.Name):
                        exc_name = handler.type.id
                    suggestions.append(
                        RefactorSuggestion(
                            file=file_path,
                            line=node.lineno,
                            pattern="suppress",
                            description=f"try/except{exc_name}/pass → contextlib.suppress",
                            before=src.strip(),
                            after=f"with suppress({exc_name}): ...",
                            confidence=0.85,
                        )
                    )

        # Pattern 5: string concat in loop → join
        if isinstance(node, (ast.For, ast.While)):
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.AugAssign)
                    and isinstance(child.op, ast.Add)
                    and isinstance(child.value, (ast.Constant, ast.JoinedStr))
                ):
                    src = (
                        source_lines[child.lineno - 1]
                        if child.lineno <= len(source_lines)
                        else ""
                    )
                    suggestions.append(
                        RefactorSuggestion(
                            file=file_path,
                            line=child.lineno,
                            pattern="join_in_loop",
                            description="String concat in loop → use ''.join()",
                            before=src.strip(),
                            after="parts = []; result = ''.join(parts)",
                            confidence=0.9,
                        )
                    )
                    break

        # Pattern 6: class without __slots__
        if isinstance(node, ast.ClassDef):
            # A @dataclass(slots=True) generates __slots__ itself; never flag it.
            is_dataclass = any(_is_dataclass_decorator(d) for d in node.decorator_list)
            has_slots = False
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name) and target.id == "__slots__":
                            has_slots = True
                elif (
                    isinstance(item, ast.AnnAssign)
                    and isinstance(item.target, ast.Name)
                    and item.target.id == "__slots__"
                ):
                    has_slots = True
            if not has_slots and not is_dataclass:
                # Skip small classes.
                methods = [
                    m
                    for m in node.body
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                if len(methods) > 2:
                    suggestions.append(
                        RefactorSuggestion(
                            file=file_path,
                            line=node.lineno,
                            pattern="add_slots",
                            description=f"Class {node.name} missing __slots__ ({len(methods)} methods)",
                            before=f"class {node.name}:",
                            after=f"class {node.name}:\n    __slots__ = ('field1', 'field2')",
                            confidence=0.6,
                        )
                    )

    return suggestions


def _count_elif_chain(node: ast.If) -> int:
    """Count the length of an if/elif chain."""
    count = 1
    current = node
    while current.orelse:
        if len(current.orelse) == 1 and isinstance(current.orelse[0], ast.If):
            count += 1
            current = current.orelse[0]
        else:
            break
    return count


# =============================================================================
# 9. Context compression — group-by-rule
# =============================================================================


def compress_compact_output(
    lint_errors: list[object],
    issues: list[object],
    security: list[object],
    complexity: list[object],
) -> str:
    """Compress compact output by grouping identical rules."""

    parts: list[str] = []

    # Group lint errors by code.
    if lint_errors:
        lint_groups: dict[str, int] = defaultdict(int)
        for e in lint_errors:
            code = getattr(e, "code", "unknown")
            lint_groups[code] += 1
        codes = ", ".join(
            f"{code}x{count}" if count > 1 else code
            for code, count in sorted(lint_groups.items(), key=lambda x: -x[1])
        )
        parts.append(f"  lint({len(lint_errors)}): {codes}")

    # Group validation issues by rule.
    if issues:
        rule_groups: dict[str, int] = defaultdict(int)
        for i in issues:
            rule = getattr(i, "rule", "unknown")
            rule_groups[rule] += 1
        rules = ", ".join(
            f"{rule}x{count}" if count > 1 else rule
            for rule, count in sorted(rule_groups.items(), key=lambda x: -x[1])
        )
        parts.append(f"  rules({len(issues)}): {rules}")

    # Group security by rule.
    if security:
        sec_groups: dict[str, int] = defaultdict(int)
        for f in security:
            rule = getattr(f, "rule", "unknown")
            sec_groups[rule] += 1
        secs = ", ".join(
            f"{rule}x{count}" if count > 1 else rule
            for rule, count in sorted(sec_groups.items(), key=lambda x: -x[1])
        )
        parts.append(f"  sec({len(security)}): {secs}")

    # Complexity — just top 3.
    if complexity:
        ccs = ", ".join(f"{c.name}({c.score})" for c in complexity[:3])
        parts.append(f"  cc({len(complexity)}): {ccs}")

    return "\n".join(parts)
