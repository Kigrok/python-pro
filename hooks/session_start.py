#!/usr/bin/env python3
# hooks/session_start.py — SessionStart hook: preload graph + project context.

from __future__ import annotations

from pathlib import Path
from sys import path as _sys_path

# Bootstrap: hook scripts run standalone, so put the plugin root on sys.path.
_ROOT: Path = Path(__file__).resolve().parent.parent
_sys_path.insert(0, str(_ROOT))

from json import dumps, loads
from sys import exit, stdin

from memory import PatternStorage


class SessionStartHook:
    """Preload graph, provide project context and recurring issues."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def _as_int(value: object) -> int:
        """Coerce a stored count to int."""
        return value if isinstance(value, int) else 0

    @staticmethod
    def _project_stats() -> str:
        """Quick project statistics."""
        try:
            from cli.codegraph import CodeGraph

            graph: CodeGraph = CodeGraph.load(root=_ROOT)
            files: int = len(graph.to_dict())
            total_imports: int = sum(
                len(n.get("imports", [])) for n in graph.to_dict().values()
            )
            return f"{files} files, {total_imports} imports"
        except (OSError, ValueError):
            return ""

    @staticmethod
    def _frequent_issues() -> str:
        """Top recurring issues to avoid."""
        frequent: list[dict[str, object]] = PatternStorage.get_frequent(3)
        if not frequent:
            return ""
        ordered: list[dict[str, object]] = sorted(
            frequent,
            key=lambda e: -SessionStartHook._as_int(e["count"]),
        )[:5]
        lines: list[str] = ["Recurring issues to avoid:"]
        entry: dict[str, object]
        for entry in ordered:
            lines.append(
                f"- {entry['linter']} {entry['code']}: " f"(seen {entry['count']}x)"
            )
        return "\n".join(lines)

    @classmethod
    def run(cls) -> int:
        """Emit additionalContext with project context and patterns."""
        parts: list[str] = []

        # Project stats.
        stats: str = cls._project_stats()
        if stats:
            parts.append(f"python-pro project: {stats}")

        # Frequent issues.
        issues: str = cls._frequent_issues()
        if issues:
            parts.append(issues)

        # Rules reminder.
        parts.append(
            "python-pro rules: no Any/Optional, __slots__, "
            "exact-name imports, match/case, PEP 257 docstrings"
        )

        context: str = "\n".join(parts)
        if context:
            print(
                dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "SessionStart",
                            "additionalContext": context,
                        },
                    }
                )
            )
        return 0


def main() -> None:
    """Read the SessionStart event (payload ignored) and run the hook."""
    try:
        loads(stdin.read() or "{}")
    except ValueError:
        exit(0)
    exit(SessionStartHook.run())


if __name__ == "__main__":
    main()
