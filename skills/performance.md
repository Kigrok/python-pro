---
name: performance
description: Performance optimization patterns — profiling, memory, speed, lazy loading, caching, generators. Activate when writing performance-critical code or after editing files with high complexity.
---

# Performance — Speed, Memory, Profiling

Patterns extracted from CPython internals and high-performance Python code.

## Prime Directive

Every function should be as fast as possible without sacrificing readability.
Profile BEFORE optimising — don't guess.

## Function Profiling

```python
# REQUIRED: use @timed to measure execution time
from cli.profiler import timed, track_memory

@timed
def process_data(items: list[str]) -> dict[str, int]:
    """Process items and return counts."""
    return {item: len(item) for item in items}

# Check stats later:
from cli.profiler import get_timing_stats
stats = get_timing_stats("module.process_data")
# → process_data: 42 calls, avg=0.23ms, min=0.12ms, max=1.89ms

# REQUIRED: use @track_memory for memory-hungry functions
@track_memory("data_loader")
def load_large_dataset(path: str) -> list[dict]:
    """Load and parse a large JSON file."""
    ...

# Memory stats:
from cli.profiler import get_memory_stats
stats = get_memory_stats("data_loader")
# → data_loader: current=12.3MB, peak=45.6MB, allocs=7
```

## One-line Profile

```python
# REQUIRED: profile a single call inline
from cli.profiler import profile_call

result = profile_call(my_function, arg1, arg2)
# Returns: {name, elapsed_ms, arg_weight, result_weight, memory_current, memory_peak}
```

## Weight Estimation

```python
# REQUIRED: estimate memory weight of any object
from cli.profiler import object_weight, format_bytes

w = object_weight({"a": [1, 2, 3], "b": "hello"})
print(format_bytes(w))  # → "192B"

# Deep weight (recursive):
from cli.profiler import deep_weight
w = deep_weight(complex_nested_object)
```

## Lazy Loading

```python
# REQUIRED: lazy-load heavy imports inside functions
def process_data() -> None:
    """Only import when needed."""
    from numpy import array  # lazy: only when called
    arr = array([1, 2, 3])

# REQUIRED: lazy module-level import for optional deps
_numpy = None

def get_numpy():
    global _numpy
    if _numpy is None:
        import numpy
        _numpy = numpy
    return _numpy
```

## Generators Over Lists

```python
# BANNED: materialising large lists unnecessarily
results = [transform(x) for x in huge_list]  # WRONG if huge_list is large

# REQUIRED: generator for large datasets
results = (transform(x) for x in huge_list)  # CORRECT — lazy

# REQUIRED: generator function for streaming
def read_large_file(path: str):
    """Yield lines one at a time — never load entire file."""
    with open(path) as f:
        for line in f:
            yield line.strip()
```

## Caching

```python
# REQUIRED: cache pure functions
from functools import lru_cache, cache

@lru_cache(maxsize=128)
def expensive_computation(n: int) -> int:
    """Cached — runs once per unique n."""
    return sum(i * i for i in range(n))

# REQUIRED: unbounded cache for truly pure functions
@cache
def fibonacci(n: int) -> int:
    """Unbounded cache — safe because input is bounded."""
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

# BANNED: caching methods with side effects
@lru_cache
def save_to_db(record: dict) -> None:  # WRONG — side effect
    db.save(record)
```

## Data Structure Selection

```python
# REQUIRED: right data structure for the job
# Lookup by key → dict (O(1))
users: dict[int, User] = {u.id: u for u in user_list}
user = users.get(user_id)

# Membership test → set (O(1))
valid_ids: set[int] = {1, 2, 3, 4, 5}
is_valid = user_id in valid_ids  # O(1)

# Ordered unique → dict (Python 3.7+)
unique = list(dict.fromkeys(duplicate_list))

# Priority queue → heapq
import heapq
top_5 = heapq.nlargest(5, items, key=lambda x: x.score)

# Counter → collections.Counter
from collections import Counter
word_counts = Counter(words)
```

## String Operations

```python
# REQUIRED: join for multiple strings
# BAD
result = ""
for s in strings:
    result += s  # O(n²) — creates new string each time

# GOOD
result = "".join(strings)  # O(n)

# REQUIRED: f-strings over .format() or %
name = "world"
greeting = f"Hello, {name}!"  # fastest
```

## Async Performance

```python
# REQUIRED: gather for concurrent I/O
from asyncio import gather

async def fetch_all(urls: list[str]) -> list[bytes]:
    """Fetch all URLs concurrently."""
    async with ClientSession() as session:
        tasks = [fetch_one(session, url) for url in urls]
        return list(await gather(*tasks))

# REQUIRED: Semaphore for concurrency limiting
from asyncio import Semaphore

sem = Semaphore(10)  # max 10 concurrent

async def limited_fetch(url: str) -> bytes:
    async with sem:
        return await fetch(url)
```

## I/O Performance

```python
# REQUIRED: async file I/O for large files
import aiofiles

async def read_file(path: str) -> str:
    async with aiofiles.open(path) as f:
        return await f.read()

# REQUIRED: buffered I/O for large writes
async def write_large(path: str, data: bytes) -> None:
    async with aiofiles.open(path, "wb") as f:
        await f.write(data)
```

## Memory Patterns

```python
# REQUIRED: __slots__ on all classes (saves ~40% memory)
class Point:
    __slots__ = ("x", "y")
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y

# REQUIRED: dataclass(slots=True) for data carriers
from dataclasses import dataclass

@dataclass(slots=True)
class Config:
    host: str
    port: int

# REQUIRED: tuple/frozenset for constants
COLORS: Final[tuple[str, ...]] = ("red", "green", "blue")
VALID_IDS: Final[frozenset[int]] = frozenset({1, 2, 3})

# BANNED: mutable default arguments
def append(item, lst=[]):  # WRONG — shared mutable default
    lst.append(item)
    return lst

def append(item, lst=None):  # CORRECT
    if lst is None:
        lst = []
    lst.append(item)
    return lst
```

## Profiling Workflow

```python
# Step 1: run smart_context to see complexity
# Step 2: use @timed on suspect functions
# Step 3: use @track_memory for memory issues
# Step 4: use profile_call for one-off measurements
# Step 5: check import_weights for heavy imports
# Step 6: check function_weights for complex functions
```

## Banned Performance Anti-patterns

- `import module` → `from module import name`
- List comprehension for filtering → generator expression
- `for` loop + `append` → list/set/dict comprehension
- Repeated string concatenation → `"".join()`
- `dict.keys()` in membership test → `key in dict`
- `len(x) > 0` → `if x:`
- `type(x) == Y` → `isinstance(x, Y)`
- `map()`/`filter()` with lambda → list comprehension
- Nested loops → `itertools.product()` or dict comprehension
