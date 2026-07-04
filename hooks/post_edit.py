#!/usr/bin/env python3
# hooks/post_edit.py — PostToolUse hook: smart context provider.

from __future__ import annotations

from pathlib import Path
from sys import path as _sys_path

# Bootstrap: hook scripts run standalone, so put the plugin root on sys.path.
_ROOT: Path = Path(__file__).resolve().parent.parent
_sys_path.insert(0, str(_ROOT))

from os import environ

# Prefer the bundled venv so ruff/black resolve when PATH lacks them.
if (_ROOT / ".venv" / "bin").is_dir():
    environ["PATH"] = f"{_ROOT / '.venv' / 'bin'}:{environ.get('PATH', '')}"

from asyncio import run
from json import dumps, loads
from sys import exit, stdin

from cli.log import get_logger
from cli.performance import PerformanceAnalyzer
from cli.runtime import RuntimeExecutor, RuntimeProfile
from cli.smart_context import SmartContextBuilder
from hooks.common import get_target

log = get_logger("post_edit")


class PostEditHook:
    """Smart context provider: all checks done, compact output for AI."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def _target(payload: dict[str, object]) -> Path | None:
        """Extract a Python file path from the PostToolUse payload."""
        result = get_target(payload, require_exists=True)
        if result:
            log.info("Target file: %s", result)
        return result

    @staticmethod
    def _performance_context(path: Path) -> str:
        """Get performance profile context for the file."""
        try:
            profile = PerformanceAnalyzer.analyze(str(path))
            parts: list[str] = []

            # Import weight.
            if profile.imports:
                heavy: list = [
                    i for i in profile.imports if i.estimated_weight > 100_000
                ]
                if heavy:
                    names: str = ", ".join(
                        f"{i.module}(~{i.estimated_weight // 1024}KB)"
                        for i in heavy[:3]
                    )
                    parts.append(f"heavy imports: {names}")

            # Complex functions.
            if profile.functions:
                complex_fns = [
                    f for f in profile.functions if f.complexity_estimate > 8
                ]
                if complex_fns:
                    names = ", ".join(
                        f"{f.name}(cc={f.complexity_estimate})" for f in complex_fns[:3]
                    )
                    parts.append(f"complex functions: {names}")

            # Missing annotations.
            no_ann = [f for f in profile.functions if not f.annotations_complete]
            if no_ann:
                parts.append(f"{len(no_ann)} function(s) missing annotations")

            # Classes without __slots__.
            no_slots = [c for c in profile.classes if not c.has_slots]
            if no_slots:
                names = ", ".join(c.name for c in no_slots[:3])
                parts.append(f"missing __slots__: {names}")

            # Deep nesting.
            if profile.nested_depth_max > 3:
                parts.append(f"nesting depth: {profile.nested_depth_max}")

            return "perf: " + "; ".join(parts) if parts else ""
        except (OSError, ValueError) as exc:
            log.warning("Performance analysis failed for %s: %s", path, exc)
            return ""

    @staticmethod
    def _runtime_context(path: Path) -> str:
        """Run the file and capture runtime errors."""
        try:
            profile: RuntimeProfile = RuntimeExecutor.execute_file(
                str(path),
                timeout=5.0,
            )
            if not profile.has_issues:
                return f"  runtime: OK ({profile.execution_time_ms:.1f}ms)"
            return f"  {profile.to_compact()}"
        except Exception as exc:  # noqa: BLE001 - profiling runs arbitrary user code
            log.warning("Runtime execution failed for %s: %s", path, exc)
            return f"  runtime: skipped ({exc})"

    @staticmethod
    async def _inspect(path: Path) -> str:
        """Run all checks, return compact context + actions."""
        # Build context once and extract both compact and actions.
        ctx = await SmartContextBuilder.build(str(path))
        compact: str = ctx.to_compact()
        actions: list[str] = ctx.to_actions()

        # Performance context.
        perf: str = PostEditHook._performance_context(path)

        # Runtime context — actually execute the file.
        runtime: str = PostEditHook._runtime_context(path)

        # Format output.
        parts: list[str] = []
        if compact:
            parts.append(compact)
        if perf:
            parts.append(f"  {perf}")
        if runtime:
            parts.append(runtime)
        if actions:
            parts.append("  → " + "; ".join(actions[:4]))
        return "\n".join(parts)

    @staticmethod
    async def run(payload: dict[str, object]) -> int:
        """Hook entry: emit additionalContext only when issues remain."""
        path: Path | None = PostEditHook._target(payload)
        if path is None:
            return 0
        log.info("PostEditHook running for %s", path)
        text: str = await PostEditHook._inspect(path)
        if text:
            log.info("Hook output:\n%s", text)
            print(
                dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PostToolUse",
                            "additionalContext": text,
                        },
                    }
                )
            )
        else:
            log.info("No issues found for %s", path)
        return 0


def main() -> None:
    """Read the PostToolUse event from stdin and run the hook."""
    log.info("PostEditHook starting")
    try:
        payload: dict[str, object] = loads(stdin.read() or "{}")
    except ValueError:
        log.warning("Failed to parse stdin payload")
        exit(0)
    exit(run(PostEditHook.run(payload)))


if __name__ == "__main__":
    main()
