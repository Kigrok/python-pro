#!/usr/bin/env python3
# cli/exec_cache.py — Cache for function execution results.

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_CACHE_DIR: Final[Path] = Path.home() / ".cache" / "python-pro" / "exec_cache"
_MAX_AGE_SECONDS: Final[int] = 3600  # 1 hour
_MAX_ENTRIES: Final[int] = 1000


@dataclass(slots=True)
class CacheEntry:
    """Single cached execution result."""

    key: str
    func_name: str
    result: object
    timestamp: float
    hit_count: int = 0

    @property
    def age_seconds(self) -> float:
        return time.time() - self.timestamp

    @property
    def is_expired(self) -> bool:
        return self.age_seconds > _MAX_AGE_SECONDS

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "func_name": self.func_name,
            "result": self.result,
            "timestamp": self.timestamp,
            "hit_count": self.hit_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> CacheEntry:
        return cls(
            key=data["key"],
            func_name=data.get("func_name", ""),
            result=data["result"],
            timestamp=data["timestamp"],
            hit_count=data.get("hit_count", 0),
        )


class ExecCache:
    """Persistent cache for function execution results."""

    __slots__: tuple[str, ...] = ("_cache", "_cache_file")

    def __init__(self, name: str = "default") -> None:
        self._cache: dict[str, CacheEntry] = {}
        self._cache_file: Path = _CACHE_DIR / f"{name}.json"
        self._load()

    def _load(self) -> None:
        """Load cache from disk."""
        try:
            data: dict[str, dict[str, object]] = json.loads(
                self._cache_file.read_text(encoding="utf-8"),
            )
            for key, entry_data in data.items():
                entry = CacheEntry.from_dict(entry_data)
                if not entry.is_expired:
                    self._cache[key] = entry
        except (OSError, json.JSONDecodeError, KeyError):
            pass

    def _save(self) -> None:
        """Save cache to disk."""
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            data = {k: v.to_dict() for k, v in self._cache.items()}
            self._cache_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except OSError:
            pass

    @staticmethod
    def _make_key(func_name: str, args: tuple, kwargs: dict) -> str:
        """Generate cache key from function name and arguments."""
        key_data = json.dumps(
            {
                "func": func_name,
                "args": args,
                "kwargs": sorted(kwargs.items()),
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    def get(self, func_name: str, args: tuple, kwargs: dict) -> object | None:
        """Get cached result or None."""
        key = self._make_key(func_name, args, kwargs)
        entry = self._cache.get(key)
        if entry is None or entry.is_expired:
            return None
        entry.hit_count += 1
        return entry.result

    def set(self, func_name: str, args: tuple, kwargs: dict, result: object) -> None:
        """Cache a result."""
        key = self._make_key(func_name, args, kwargs)
        self._cache[key] = CacheEntry(
            key=key,
            func_name=func_name,
            result=result,
            timestamp=time.time(),
        )
        # Evict old entries if too many.
        if len(self._cache) > _MAX_ENTRIES:
            oldest = sorted(
                self._cache.values(),
                key=lambda e: e.timestamp,
            )[: len(self._cache) - _MAX_ENTRIES]
            for entry in oldest:
                del self._cache[entry.key]
        self._save()

    def invalidate(self, func_name: str) -> int:
        """Invalidate all entries for a function. Returns count removed."""
        removed: int = 0
        keys_to_remove: list[str] = [
            k for k, v in self._cache.items() if v.func_name == func_name
        ]
        for k in keys_to_remove:
            del self._cache[k]
            removed += 1
        if removed:
            self._save()
        return removed

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        self._save()

    def stats(self) -> dict[str, int]:
        """Get cache statistics."""
        total_hits = sum(e.hit_count for e in self._cache.values())
        expired = sum(1 for e in self._cache.values() if e.is_expired)
        return {
            "entries": len(self._cache),
            "total_hits": total_hits,
            "expired": expired,
            "max_entries": _MAX_ENTRIES,
        }


def cached_exec(func_name: str | None = None):
    """Decorator: cache function execution results.

    Usage:
        @cached_exec()
        def expensive(n: int) -> int:
            return sum(i * i for i in range(n))

        # First call: computes and caches
        # Second call: returns from cache
    """
    import functools

    def decorator(func):
        name = func_name or f"{func.__module__}.{func.__qualname__}"
        cache = ExecCache(name)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = cache.get(name, args, kwargs)
            if result is not None:
                return result
            result = func(*args, **kwargs)
            cache.set(name, args, kwargs, result)
            return result

        wrapper.cache_clear = cache.clear  # type: ignore[attr-defined]
        wrapper.cache_stats = cache.stats  # type: ignore[attr-defined]
        return wrapper

    return decorator
