#!/usr/bin/env python3
# hooks/pre_edit.py — PreToolUse hook: validate before AI writes.

from __future__ import annotations

from pathlib import Path
from sys import path as _sys_path

# Bootstrap: hook scripts run standalone, so put the plugin root on sys.path.
_ROOT: Path = Path(__file__).resolve().parent.parent
_sys_path.insert(0, str(_ROOT))

from json import dumps, loads  # noqa: E402
from sys import exit, stdin  # noqa: E402

from hooks.common import get_target  # noqa: E402


class PreEditHook:
    """Validate before AI writes: file context, tests, graph info."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def _target(payload: dict[str, object]) -> Path | None:
        """Extract a Python file path from the PreToolUse payload."""
        return get_target(payload, require_exists=False)

    @staticmethod
    def _existing_file_context(path: Path) -> str:
        """If file exists, provide summary of contents."""
        if not path.exists():
            return f"NEW FILE: {path.name}"

        try:
            source: str = path.read_text(encoding="utf-8", errors="replace")
            lines: int = source.count("\n") + 1
            return f"EXISTS: {path.name} ({lines} lines)"
        except OSError:
            return f"EXISTS: {path.name} (cannot read)"

    @staticmethod
    def _test_context(path: Path) -> str:
        """Find and report related test files."""
        tests: list[str] = []
        name: str = path.stem

        # Direct test file.
        if name.startswith("test_") or name.endswith("_test"):
            tests.append(str(path))

        # Look for test_{stem}.py
        test_file: Path = path.parent / f"test_{name}.py"
        if test_file.exists():
            tests.append(str(test_file))

        # Look in tests/ directory.
        tests_dir: Path = path.parent.parent / "tests"
        if tests_dir.exists():
            for tf in tests_dir.rglob(f"test_{name}.py"):
                tests.append(str(tf))

        if not tests:
            return ""
        unique: list[str] = list(dict.fromkeys(tests))
        return f"TESTS: {', '.join(Path(t).name for t in unique[:3])}"

    @staticmethod
    def _graph_context(path: Path) -> str:
        """What this file exports and what depends on it."""
        try:
            from cli.codegraph import CodeGraph

            graph: CodeGraph = CodeGraph.load(root=path.parent.parent)
            exports: list[str] = graph.exports_of(str(path))
            affected: list[str] = graph.affected_by(str(path))
            parts: list[str] = []
            if exports:
                parts.append(f"exports: {', '.join(exports[:5])}")
            if affected:
                parts.append(
                    f"affects: {', '.join(Path(a).name for a in affected[:3])}"
                )
            return ", ".join(parts) if parts else ""
        except (OSError, ValueError):
            return ""

    @classmethod
    def run(cls, payload: dict[str, object]) -> int:
        """Emit additionalContext before AI writes a file."""
        path: Path | None = cls._target(payload)
        if path is None:
            return 0

        parts: list[str] = []
        parts.append(cls._existing_file_context(path))

        test_ctx: str = cls._test_context(path)
        if test_ctx:
            parts.append(test_ctx)

        graph_ctx: str = cls._graph_context(path)
        if graph_ctx:
            parts.append(graph_ctx)

        context: str = " | ".join(parts)
        if context:
            print(
                dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "additionalContext": context,
                        },
                    }
                )
            )
        return 0


def main() -> None:
    """Read the PreToolUse event from stdin and run the hook."""
    try:
        payload: dict[str, object] = loads(stdin.read() or "{}")
    except ValueError:
        exit(0)
    exit(PreEditHook.run(payload))


if __name__ == "__main__":
    main()
