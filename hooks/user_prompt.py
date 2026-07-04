#!/usr/bin/env python3
# hooks/user_prompt.py — Surface the python-pro standard on relevant prompts.

from __future__ import annotations

from pathlib import Path
from sys import path as _sys_path

# Bootstrap: hook scripts run standalone, so put the plugin root on sys.path.
_ROOT: Path = Path(__file__).resolve().parent.parent
_sys_path.insert(0, str(_ROOT))

from json import dumps, loads
from sys import exit, stdin
from typing import Final

from memory import PatternStorage

_TRIGGERS: Final[tuple[str, ...]] = (
    "python",
    ".py",
    "async",
    "asyncio",
    "fastapi",
    "sqlalchemy",
    "pydantic",
    "pytest",
    "mypy",
    "ruff",
    "type hint",
    "annotation",
    "dataclass",
)
_STANDARD: Final[str] = (
    "python-pro standard in effect: strict typing (no Any/Optional, use X | None), "
    "__slots__ on non-dataclass classes, ClassVar for class constants, exact-name "
    "imports (from x import y), match/case for 3+ branches, PEP 257 docstrings "
    "on public objects, Decimal for money, small single-purpose functions. Prefer the "
    "standard library by default — add a third-party dependency only when stdlib "
    "cannot reasonably do the job; when you do, choose secure, low-level, fast, async "
    "libraries (asyncpg/aiohttp/msgspec, not psycopg2/requests/pickle). Use the "
    "python-pro MCP tools (validate_file, lint_file, analyze_types, "
    "check_stdlib) to verify."
)


class UserPromptHook:
    """Injects the python-pro standard when a prompt looks Python-related."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def _as_int(value: object) -> int:
        """Coerce a stored count to int."""
        return value if isinstance(value, int) else 0

    @staticmethod
    def _is_relevant(prompt: str) -> bool:
        """True when the prompt mentions Python work."""
        low: str = prompt.lower()
        return any(trigger in low for trigger in _TRIGGERS)

    @classmethod
    def _patterns_note(cls) -> str:
        """A short note of the most frequent recorded mistakes, if any."""
        frequent: list[dict[str, object]] = PatternStorage.get_frequent(2)
        if not frequent:
            return ""
        top: list[dict[str, object]] = sorted(
            frequent,
            key=lambda e: -cls._as_int(e["count"]),
        )[:3]
        items: list[str] = [f"{e['linter']} {e['code']}" for e in top]
        return " Recurring issues to avoid: " + ", ".join(items) + "."

    @classmethod
    def run(cls, payload: dict[str, object]) -> int:
        """Emit additionalContext when the prompt is Python-related."""
        prompt: object = payload.get("prompt", "")
        if not isinstance(prompt, str) or not cls._is_relevant(prompt):
            return 0
        context: str = _STANDARD + cls._patterns_note()
        print(
            dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": context,
                    },
                }
            )
        )
        return 0


def main() -> None:
    """Read the UserPromptSubmit event from stdin and run the hook."""
    try:
        payload: dict[str, object] = loads(stdin.read() or "{}")
    except ValueError:
        exit(0)
    exit(UserPromptHook.run(payload))


if __name__ == "__main__":
    main()
