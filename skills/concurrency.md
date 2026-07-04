---
name: concurrency
description: Concurrency patterns from CPython — asyncio, threading, multiprocessing, TaskGroup, Semaphore. Activate when writing concurrent/parallel code.
---

# Concurrency — CPython Patterns

Professional async/parallel patterns from https://github.com/python/cpython.

## asyncio.TaskGroup (Python 3.11+)

```python
# REQUIRED: TaskGroup for structured concurrency
import asyncio

async def fetch_all(urls: list[str]) -> list[bytes]:
    """Fetch all URLs concurrently with TaskGroup."""
    results: list[bytes] = []
    async with asyncio.TaskGroup() as tg:
        for url in urls:
            results.append(tg.create_task(fetch_one(url)))
    return [r.result() for r in results]

# WHY: TaskGroup ensures all tasks complete or all fail
# No orphaned tasks, proper exception propagation
```

## Semaphore for Rate Limiting

```python
# REQUIRED: Semaphore to limit concurrency
import asyncio

sem = asyncio.Semaphore(10)  # max 10 concurrent

async def limited_fetch(url: str) -> bytes:
    """Fetch with concurrency limit."""
    async with sem:
        return await fetch(url)

async def fetch_all(urls: list[str]) -> list[bytes]:
    """Fetch all URLs with rate limiting."""
    tasks = [limited_fetch(url) for url in urls]
    return list(await asyncio.gather(*tasks))
```

## Timeout Patterns

```python
# REQUIRED: asyncio.timeout for deadlines (Python 3.11+)
async def slow_operation() -> Result:
    """Operation with timeout."""
    async with asyncio.timeout(5.0):  # 5 second deadline
        return await fetch_huge_data()

# REQUIRED: asyncio.wait_for for task timeout
try:
    result = await asyncio.wait_for(slow_operation(), timeout=5.0)
except asyncio.TimeoutError:
    log.warning("Operation timed out")
```

## Producer-Consumer

```python
# REQUIRED: Queue for producer-consumer pattern
import asyncio

async def producer(queue: asyncio.Queue, items: list[str]) -> None:
    """Produce items into queue."""
    for item in items:
        await queue.put(item)
    await queue.put(None)  # sentinel

async def consumer(queue: asyncio.Queue) -> None:
    """Consume items from queue."""
    while True:
        item = await queue.get()
        if item is None:
            break
        await process(item)
        queue.task_done()

async def run_producer_consumer() -> None:
    """Run producer-consumer pipeline."""
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=10)
    await asyncio.gather(
        producer(queue, ["a", "b", "c"]),
        consumer(queue),
    )
```

## Thread Pool for CPU-Bound Work

```python
# REQUIRED: to_thread for blocking I/O
import asyncio
from pathlib import Path

async def read_file(path: str) -> str:
    """Read file without blocking event loop."""
    return await asyncio.to_thread(Path(path).read_text)

# REQUIRED: ProcessPoolExecutor for CPU-bound work
from concurrent.futures import ProcessPoolExecutor

executor = ProcessPoolExecutor(max_workers=4)

async def compute_heavy(data: list[int]) -> list[int]:
    """Run CPU-heavy computation in process pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, process_data, data)
```

## Async Context Managers

```python
# REQUIRED: async context managers for resource lifecycle
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_session():
    """Provide async database session."""
    session = async_session()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

# Usage:
async with get_session() as session:
    await session.execute(select(User))
```

## Async Generators

```python
# REQUIRED: async generators for streaming data
async def stream_lines(path: str):
    """Yield lines from file asynchronously."""
    async with aiofiles.open(path) as f:
        async for line in f:
            yield line.rstrip("\n")

# Usage:
async for line in stream_lines("data.txt"):
    process(line)
```

## Thread Safety

```python
# REQUIRED: Lock for shared state
import asyncio

class Counter:
    """Thread-safe counter."""
    def __init__(self) -> None:
        self._count: int = 0
        self._lock: asyncio.Lock = asyncio.Lock()

    async def increment(self) -> int:
        async with self._lock:
            self._count += 1
            return self._count

# REQUIRED: asyncio.Queue for thread-safe communication
queue: asyncio.Queue[str] = asyncio.Queue()
```

## Banned Anti-patterns

- `asyncio.run()` inside async code → use `await` directly
- `time.sleep()` in async → `await asyncio.sleep()`
- Blocking I/O in async → `asyncio.to_thread()` or async library
- Unbounded queues → set `maxsize`
- Fire-and-forget tasks → use TaskGroup or gather
- `loop.create_task()` without reference → store task reference
- Global event loop → use `asyncio.get_event_loop()` or `asyncio.Runner`
