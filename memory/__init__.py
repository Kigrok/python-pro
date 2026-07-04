#!/usr/bin/env python3
# memory/__init__.py — PatternStorage for learned error patterns.

from __future__ import annotations

from datetime import UTC, datetime
from json import dumps, loads
from pathlib import Path
from typing import Final

MEMORY_DIR: Final[Path] = Path(__file__).parent
PATTERNS_FILE: Final[Path] = MEMORY_DIR / "patterns.json"


class PatternStorage:
    """Stores and retrieves learned error patterns."""

    __slots__: tuple[str, ...] = ()
    _cache: dict[str, dict[str, object]] | None = None

    @staticmethod
    def _as_int(value: object) -> int:
        """Coerce a JSON-loaded value to int."""
        return value if isinstance(value, int) else int(str(value))

    @classmethod
    def _load(cls) -> dict[str, dict[str, object]]:
        """Load patterns from JSON file (cached in memory)."""
        if cls._cache is not None:
            return cls._cache
        if PATTERNS_FILE.exists():
            cls._cache = loads(PATTERNS_FILE.read_text())
            return cls._cache
        cls._cache = {}
        return cls._cache

    @classmethod
    def _save(cls, patterns: dict[str, dict[str, object]]) -> None:
        """Save patterns to JSON file."""
        cls._cache = patterns
        PATTERNS_FILE.write_text(
            dumps(patterns, indent=2, ensure_ascii=False),
        )

    @classmethod
    def record_batch(cls, records: list[dict[str, object]]) -> None:
        """Batch-record multiple patterns in one load/save cycle."""
        if not records:
            return
        patterns: dict[str, dict[str, object]] = cls._load()
        now: str = datetime.now(UTC).isoformat()
        rec: dict[str, object]
        for rec in records:
            linter: str = str(rec.get("linter", ""))
            code: str = str(rec.get("code", ""))
            key: str = f"{linter}:{code}"
            entry: dict[str, object]
            if key in patterns:
                entry = patterns[key]
                entry["count"] = cls._as_int(entry["count"]) + 1
                entry["last_seen"] = now
            else:
                entry = {
                    "linter": linter,
                    "code": code,
                    "message": rec.get("message", ""),
                    "fix": rec.get("fix", ""),
                    "count": 1,
                    "first_seen": now,
                    "last_seen": now,
                }
                patterns[key] = entry
        cls._save(patterns)

    @staticmethod
    def record(
        linter: str,
        code: str,
        message: str,
        fix: str,
        file_path: str = "",
        line: int = 0,
    ) -> dict[str, object]:
        """Record an error pattern for learning."""
        patterns: dict[str, dict[str, object]] = PatternStorage._load()
        key: str = f"{linter}:{code}"

        entry: dict[str, object]
        if key in patterns:
            entry = patterns[key]
            entry["count"] = PatternStorage._as_int(entry["count"]) + 1
            entry["last_seen"] = datetime.now(UTC).isoformat()
        else:
            entry = {
                "linter": linter,
                "code": code,
                "message": message,
                "fix": fix,
                "count": 1,
                "first_seen": datetime.now(UTC).isoformat(),
                "last_seen": datetime.now(UTC).isoformat(),
            }
            patterns[key] = entry

        PatternStorage._save(patterns)
        return entry

    @staticmethod
    def get_frequent(min_count: int = 3) -> list[dict[str, object]]:
        """Get patterns seen at least min_count times."""
        patterns: dict[str, dict[str, object]] = PatternStorage._load()
        return [
            entry
            for entry in patterns.values()
            if PatternStorage._as_int(entry["count"]) >= min_count
        ]

    @staticmethod
    def get_all() -> dict[str, dict[str, object]]:
        """Get all stored patterns."""
        return PatternStorage._load()

    @staticmethod
    def format_for_skill() -> str:
        """Format frequent patterns as markdown for SKILL.md."""
        frequent: list[dict[str, object]] = PatternStorage.get_frequent(3)
        if not frequent:
            return ""

        lines: list[str] = ["## Frequent Error Patterns\n"]
        p: dict[str, object]
        for p in sorted(frequent, key=lambda x: -PatternStorage._as_int(x["count"])):
            lines.append(
                f"- `{p['linter']}` {p['code']}: {p['message']} "
                f"(fix: {p['fix']}, seen {p['count']}x)",
            )
        return "\n".join(lines)
