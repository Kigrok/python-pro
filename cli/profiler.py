#!/usr/bin/env python3
# cli/profiler.py — Lightweight profiling: @timed, @track_memory, weight analysis.

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from sys import getsizeof
from time import perf_counter_ns
from tracemalloc import get_traced_memory, is_tracing, start, stop, take_snapshot
from typing import Final, TypeVar

F = TypeVar("F", bound=Callable[..., object])

_TUPLE_SIZE: Final[int] = getsizeof(())
_LIST_SIZE: Final[int] = getsizeof([])
_DICT_SIZE: Final[int] = getsizeof({})
_SET_SIZE: Final[int] = getsizeof(set())
_STR_PER_CHAR: Final[int] = getsizeof("") // 2  # approx


def object_weight(obj: object) -> int:
    """Estimate shallow memory weight of a Python object in bytes."""
    t: type = type(obj)
    if t is int:
        return getsizeof(obj)
    if t is float:
        return getsizeof(obj)
    if t is str:
        return getsizeof(obj)
    if t is bool:
        return getsizeof(obj)
    if t is bytes:
        return getsizeof(obj)
    if t is tuple:
        return _TUPLE_SIZE + sum(object_weight(x) for x in obj)
    if t is list:
        return _LIST_SIZE + sum(object_weight(x) for x in obj)
    if t is dict:
        return _DICT_SIZE + sum(
            object_weight(k) + object_weight(v) for k, v in obj.items()
        )
    if t is set or t is frozenset:
        return _SET_SIZE + sum(object_weight(x) for x in obj)
    if t.__name__ == "ModuleType":
        return getsizeof(obj.__dict__)
    # dataclass / __slots__ / generic object.
    if hasattr(obj, "__slots__"):
        return sum(getsizeof(getattr(obj, s, None)) for s in obj.__slots__)
    if hasattr(obj, "__dict__"):
        return _DICT_SIZE + sum(
            object_weight(k) + object_weight(v) for k, v in obj.__dict__.items()
        )
    return getsizeof(obj)


def deep_weight(obj: object, _seen: set[int] | None = None) -> int:
    """Recursively estimate memory weight of an object and its contents."""
    oid: int = id(obj)
    if _seen is None:
        _seen = set()
    if oid in _seen:
        return 0
    _seen.add(oid)
    base: int = object_weight(obj)
    t: type = type(obj)
    if t is dict:
        return base + sum(
            deep_weight(k, _seen) + deep_weight(v, _seen) for k, v in obj.items()
        )
    if t is list or t is tuple or t is set or t is frozenset:
        return base + sum(deep_weight(x, _seen) for x in obj)
    if hasattr(obj, "__dict__"):
        return base + sum(deep_weight(v, _seen) for v in obj.__dict__.values())
    return base


def format_bytes(n: int) -> str:
    """Human-readable byte size."""
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f}KB"
    return f"{n / (1024 * 1024):.1f}MB"


@dataclass(slots=True)
class TimingStats:
    """Result of @timed decorator."""

    name: str
    calls: int = 0
    total_ns: int = 0
    min_ns: int = 0
    max_ns: int = 0

    @property
    def avg_ns(self) -> float:
        return self.total_ns / self.calls if self.calls else 0.0

    @property
    def avg_ms(self) -> float:
        return self.avg_ns / 1_000_000

    def __str__(self) -> str:
        return (
            f"{self.name}: {self.calls} calls, "
            f"avg={self.avg_ms:.2f}ms, "
            f"min={self.min_ns / 1_000_000:.2f}ms, "
            f"max={self.max_ns / 1_000_000:.2f}ms, "
            f"total={self.total_ns / 1_000_000:.2f}ms"
        )


@dataclass(slots=True)
class MemorySnapshot:
    """Memory allocation delta during a tracked block."""

    name: str
    current_bytes: int = 0
    peak_bytes: int = 0
    allocations: int = 0

    def __str__(self) -> str:
        return (
            f"{self.name}: current={format_bytes(self.current_bytes)}, "
            f"peak={format_bytes(self.peak_bytes)}, "
            f"allocs={self.allocations}"
        )


# ---------------------------------------------------------------------------
# Global stats store.
# ---------------------------------------------------------------------------

_TIMING_STORE: Final[dict[str, TimingStats]] = {}
_MEMORY_STORE: Final[dict[str, MemorySnapshot]] = {}


def get_timing_stats(name: str | None = None) -> list[TimingStats]:
    """Get all timing stats or stats for a specific function."""
    if name:
        s = _TIMING_STORE.get(name)
        return [s] if s else []
    return sorted(_TIMING_STORE.values(), key=lambda s: -s.total_ns)


def get_memory_stats(name: str | None = None) -> list[MemorySnapshot]:
    """Get all memory stats or stats for a specific name."""
    if name:
        s = _MEMORY_STORE.get(name)
        return [s] if s else []
    return sorted(_MEMORY_STORE.values(), key=lambda s: -s.peak_bytes)


def clear_stats() -> None:
    """Clear all collected stats."""
    _TIMING_STORE.clear()
    _MEMORY_STORE.clear()


# ---------------------------------------------------------------------------
# Decorators.
# ---------------------------------------------------------------------------


def timed(func: F) -> F:
    """Decorator: measure execution time with ns precision.

    Usage:
        @timed
        def slow():
            ...

        # Later:
        print(get_timing_stats("slow"))
    """

    @wraps(func)
    def wrapper(*args: object, **kwargs: object) -> object:
        name: str = f"{func.__module__}.{func.__qualname__}"
        t0: int = perf_counter_ns()
        result: object = func(*args, **kwargs)
        elapsed: int = perf_counter_ns() - t0

        stats: TimingStats | None = _TIMING_STORE.get(name)
        if stats is None:
            stats = TimingStats(
                name=name,
                calls=1,
                total_ns=elapsed,
                min_ns=elapsed,
                max_ns=elapsed,
            )
            _TIMING_STORE[name] = stats
        else:
            stats.calls += 1
            stats.total_ns += elapsed
            if elapsed < stats.min_ns:
                stats.min_ns = elapsed
            if elapsed > stats.max_ns:
                stats.max_ns = elapsed
        return result

    return wrapper  # type: ignore[return-value]


def track_memory(name: str | None = None) -> Callable[[F], F]:
    """Decorator: track memory allocation via tracemalloc.

    Usage:
        @track_memory()
        def allocates():
            return [1, 2, 3]

        @track_memory("custom_name")
        def allocates2():
            return {"a": 1}
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: object, **kwargs: object) -> object:
            label: str = name or f"{func.__module__}.{func.__qualname__}"

            was_running: bool = is_tracing()
            if not was_running:
                start()

            snap_before: object = take_snapshot()
            result: object = func(*args, **kwargs)
            snap_after: object = take_snapshot()

            stats_diff: list[object] = snap_after.compare_to(snap_before, "lineno")
            current: int = sum(s.size_diff for s in stats_diff if s.size_diff > 0)
            peak: int = get_traced_memory()[1]

            mem_stats: MemorySnapshot | None = _MEMORY_STORE.get(label)
            if mem_stats is None:
                mem_stats = MemorySnapshot(
                    name=label,
                    current_bytes=current,
                    peak_bytes=peak,
                    allocations=1,
                )
                _MEMORY_STORE[label] = mem_stats
            else:
                mem_stats.current_bytes = current
                if peak > mem_stats.peak_bytes:
                    mem_stats.peak_bytes = peak
                mem_stats.allocations += 1

            if not was_running:
                stop()

            return result

        return wrapper  # type: ignore[return-value]

    return decorator


def estimate_args_weight(*args: object, **kwargs: object) -> int:
    """Estimate total memory weight of function arguments."""
    total: int = sum(object_weight(a) for a in args)
    total += sum(object_weight(v) for v in kwargs.values())
    return total


def profile_call(func: F, *args: object, **kwargs: object) -> dict[str, object]:
    """Profile a single function call: timing + memory + arg weight."""
    name: str = f"{func.__module__}.{func.__qualname__}"
    arg_weight: int = estimate_args_weight(*args, **kwargs)

    was_running: bool = is_tracing()
    if not was_running:
        start()

    snap_before: object = take_snapshot()
    t0: int = perf_counter_ns()
    result: object = func(*args, **kwargs)
    elapsed: int = perf_counter_ns() - t0
    snap_after: object = take_snapshot()

    stats_diff: list[object] = snap_after.compare_to(snap_before, "lineno")
    current_alloc: int = sum(s.size_diff for s in stats_diff if s.size_diff > 0)
    peak: int = get_traced_memory()[1]
    result_weight: int = object_weight(result)

    if not was_running:
        stop()

    return {
        "name": name,
        "elapsed_ms": elapsed / 1_000_000,
        "arg_weight": format_bytes(arg_weight),
        "result_weight": format_bytes(result_weight),
        "memory_current": format_bytes(current_alloc),
        "memory_peak": format_bytes(peak),
    }
