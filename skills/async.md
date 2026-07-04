#!/usr/bin/env python3
# skills/async.md — PEP 492/525/530/3156: Async Patterns.

# Python Async — PEP 492, 525, 530, 3156

## TaskGroup (Python 3.11+)

```python
async def fetch_all(urls: list[str]) -> list[dict]:
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(fetch(url)) for url in urls]
    return [t.result() for t in tasks]
```

## Semaphore — Limit Concurrency

```python
sem = asyncio.Semaphore(10)

async def limited_fetch(url: str) -> dict:
    async with sem:
        return await fetch(url)

async def fetch_all(urls: list[str]) -> list[dict]:
    async with asyncio.TaskGroup() as tg:
        for url in urls:
            tg.create_task(limited_fetch(url))
```

## Timeout — Always Protect I/O

```python
from asyncio import wait_for, TimeoutError

async def safe_fetch(url: str) -> dict:
    try:
        return await wait_for(fetch(url), timeout=30.0)
    except TimeoutError:
        return {"error": "timeout"}
```

## Lock — Protect Shared State

```python
lock = asyncio.Lock()

async def safe_update() -> None:
    async with lock:
        shared_state += 1
```

## Queue — Producer/Consumer

```python
queue = asyncio.Queue(maxsize=100)

async def producer() -> None:
    for item in items:
        await queue.put(item)

async def consumer() -> None:
    while True:
        item = await queue.get()
        await process(item)
        queue.task_done()
```

## Thread Executor — CPU-bound

```python
from concurrent.futures import ProcessPoolExecutor

executor = ProcessPoolExecutor()

async def cpu_heavy(data: bytes) -> dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, process_data, data)
```

## Async Context Manager

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

@asynccontextmanager
async def get_session() -> AsyncIterator[ClientSession]:
    session = ClientSession()
    try:
        yield session
    finally:
        await session.close()
```

## Async Iterator — Streaming

```python
from collections.abc import AsyncIterator

async def stream_chunks(url: str) -> AsyncIterator[bytes]:
    async with client.get(url) as resp:
        async for chunk in resp.content.iter_any():
            yield chunk
```

## Correctness Rules

- `TaskGroup` over `gather` for related tasks — a failure cancels siblings and errors
  surface as an `ExceptionGroup` (`except*`).
- Keep a strong reference to every `create_task(...)` — the loop holds only weak refs,
  so an unreferenced task can be GC'd mid-run. Retrieve its exception too.
- Re-raise `CancelledError` after cleanup — never swallow it (it drives structured
  cancellation in `TaskGroup` / `timeout`).
- `async with asyncio.timeout(s):` over `wait_for(...)` (3.11+); catch `TimeoutError`
  outside the block.
- Never block the loop: offload sync/CPU work via `to_thread(...)` / `run_in_executor`.
- `get_running_loop()` inside a coroutine — never `get_event_loop()`.
- From another OS thread, schedule onto the loop only via `run_coroutine_threadsafe` /
  `call_soon_threadsafe` (asyncio objects are not thread-safe).
- Close async generators on early exit: `async with aclosing(agen) as g:`.
- `await asyncio.sleep(0)` to yield inside a long CPU loop in a coroutine.
- Entry point: `asyncio.run(main())` — never `loop.run_until_complete` or a manual loop.
