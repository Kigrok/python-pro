#!/usr/bin/env python3
# tests/test_benchmarks.py — Performance benchmarks for optimization regression detection.

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

_ROOT: Path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


def _bench(name: str, func, iterations: int = 10) -> dict[str, object]:
    """Run a benchmark and return stats."""
    times: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        func()
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000)  # ms

    avg = sum(times) / len(times)
    mn = min(times)
    mx = max(times)
    p50 = sorted(times)[len(times) // 2]
    return {
        "name": name,
        "iterations": iterations,
        "avg_ms": round(avg, 2),
        "min_ms": round(mn, 2),
        "max_ms": round(mx, 2),
        "p50_ms": round(p50, 2),
    }


def bench_ast_cache() -> None:
    """Benchmark: AST cache hit vs miss."""
    from cli.optimizations import ast_cache_stats, parse_ast_cached

    # Cold: parse without cache.
    for fp in ["cli/profiler.py", "cli/runtime.py", "cli/pipeline.py"]:
        parse_ast_cached.__wrapped__ = None  # type: ignore
        parse_ast_cached(fp)

    # Warm: parse with cache hit.
    stats = []
    for fp in ["cli/profiler.py", "cli/runtime.py", "cli/pipeline.py"]:
        r = _bench(f"ast_cache_hit:{fp}", lambda fp=fp: parse_ast_cached(fp))
        stats.append(r)

    cache = ast_cache_stats()
    print(f"  AST cache: {cache['entries']} entries")
    for s in stats:
        print(f"    {s['name']}: avg={s['avg_ms']}ms, p50={s['p50_ms']}ms")


def bench_mcp_cache() -> None:
    """Benchmark: MCP cache hit vs miss."""
    from cli.optimizations import mcp_cache, mcp_cache_clear

    call_count = 0

    @mcp_cache(ttl=5.0)
    def expensive_func(x: int) -> int:
        nonlocal call_count
        call_count += 1
        return x * x

    # Cold calls.
    call_count = 0
    for i in range(10):
        expensive_func(i)
    assert call_count == 10

    # Warm calls (cached).
    call_count = 0
    for i in range(10):
        expensive_func(i)
    assert call_count == 0, f"Expected 0 calls, got {call_count}"
    print("  MCP cache: 10/10 hits (0 actual calls)")

    mcp_cache_clear()


def bench_smart_context() -> None:
    """Benchmark: SmartContext build time."""
    from cli.smart_context import SmartContextBuilder

    async def build():
        return await SmartContextBuilder.build("cli/profiler.py")

    # Force rebuild.
    from cli.cache import SemanticCache

    SemanticCache.mark_clean.__wrapped__ = None  # type: ignore

    r = _bench("smart_context_build", lambda: asyncio.run(build()))
    print(f"  SmartContext: avg={r['avg_ms']}ms, p50={r['p50_ms']}ms")


def bench_delta() -> None:
    """Benchmark: Delta computation."""
    from cli.optimizations import compute_delta

    sections = {
        "source_hash": "abc123",
        "size": "12345",
        "lines": "500",
    }

    # First run (all new).
    r1 = _bench("delta_first_run", lambda: compute_delta("bench.py", sections))

    # Second run (all cached).
    r2 = _bench("delta_cache_hit", lambda: compute_delta("bench.py", sections))

    # Third run (one changed).
    sections["size"] = "12346"
    r3 = _bench("delta_one_change", lambda: compute_delta("bench.py", sections))

    print(
        f"  Delta: first={r1['avg_ms']}ms, cached={r2['avg_ms']}ms, changed={r3['avg_ms']}ms"
    )


def bench_refactor_detect() -> None:
    """Benchmark: Refactor suggestion detection."""
    from cli.optimizations import detect_refactor_opportunities, parse_ast_cached

    tree = parse_ast_cached("cli/profiler.py")
    r = _bench(
        "refactor_detect",
        lambda: detect_refactor_opportunities("cli/profiler.py", tree),
    )
    print(f"  Refactor detect: avg={r['avg_ms']}ms, p50={r['p50_ms']}ms")


def bench_batch_parse() -> None:
    """Benchmark: Batch AST parsing with cache."""
    from cli.optimizations import batch_parse

    files = [
        "cli/profiler.py",
        "cli/runtime.py",
        "cli/pipeline.py",
        "cli/smart_context.py",
        "cli/codegraph.py",
    ]

    r = _bench("batch_parse_5", lambda: batch_parse(files))
    print(f"  Batch parse (5 files): avg={r['avg_ms']}ms, p50={r['p50_ms']}ms")


def bench_format_bytes() -> None:
    """Benchmark: format_bytes speed."""
    from cli.profiler import format_bytes

    r = _bench("format_bytes_1000", lambda: [format_bytes(i) for i in range(1000)])
    print(f"  format_bytes (1000x): avg={r['avg_ms']}ms")


def main() -> None:
    """Run all benchmarks."""
    print("=" * 60)
    print("python-pro performance benchmarks")
    print("=" * 60)

    bench_ast_cache()
    print()
    bench_mcp_cache()
    print()
    bench_delta()
    print()
    bench_refactor_detect()
    print()
    bench_batch_parse()
    print()
    bench_format_bytes()
    print()
    bench_smart_context()

    print()
    print("=" * 60)
    print("Benchmarks complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
