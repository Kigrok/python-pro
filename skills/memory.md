---
name: memory
description: Memory optimization — __slots__, generators, data structures, lazy evaluation, profiling. Activate when writing memory-sensitive code or after detecting high memory usage.
---

# Memory Optimization

Patterns from CPython for minimal memory footprint.

## Prime Directive

Use the least memory possible while maintaining clarity.
Profile memory BEFORE optimising — don't guess.

## `__slots__` — Mandatory on All Classes

```python
# REQUIRED: __slots__ on EVERY class (saves 40-60% memory)
class Point:
    __slots__ = ("x", "y")

    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y

# REQUIRED: dataclass(slots=True)
@dataclass(slots=True)
class User:
    id: int
    name: str
    email: str

# BANNED: classes without __slots__
class Bad:  # WRONG — wastes memory
    def __init__(self, x):
        self.x = x

# Why: without __slots__, each instance has a __dict__ (~100 bytes overhead)
# With __slots__, instances use ~40% less memory
```

## Generators Over Lists

```python
# REQUIRED: generators for large datasets
# BAD — loads everything into memory
def get_all_users() -> list[User]:
    return [User(**row) for row in db.execute("SELECT * FROM users")]

# GOOD — streams one at a time
def get_all_users() -> Generator[User, None, None]:
    for row in db.execute("SELECT * FROM users"):
        yield User(**row)

# REQUIRED: generator expressions over list comprehensions
# BAD
squares = [x * x for x in range(10_000_000)]  # 80MB

# GOOD
squares = (x * x for x in range(10_000_000))  # ~0 bytes (lazy)

# REQUIRED: use map/filter for simple transforms
# BAD
results = [x * 2 for x in items if x > 0]

# GOOD (more memory-efficient for simple operations)
results = list(map(lambda x: x * 2, filter(lambda x: x > 0, items)))
```

## Tuple and Frozenset for Constants

```python
# REQUIRED: tuple for immutable sequences
COLORS: Final[tuple[str, ...]] = ("red", "green", "blue")
COORDINATES: Final[tuple[int, ...]] = (10, 20, 30)

# REQUIRED: frozenset for immutable sets
VALID_IDS: Final[frozenset[int]] = frozenset({1, 2, 3, 4, 5})
KEYWORDS: Final[frozenset[str]] = frozenset({"if", "else", "while", "for"})

# BANNED: mutable default arguments
def process(items: list[int] = []):  # WRONG — shared mutable default
    items.append(1)
    return items

def process(items: list[int] | None = None):  # CORRECT
    if items is None:
        items = []
    items.append(1)
    return items
```

## String Memory

```python
# REQUIRED: f-strings (fastest, most memory-efficient)
name = "world"
greeting = f"Hello, {name}!"  # Best

# BANNED: .format() or % for simple cases
greeting = "Hello, {}!".format(name)  # Slower
greeting = "Hello, %s!" % name  # Slowest

# REQUIRED: join for string concatenation
# BAD — O(n²) memory
result = ""
for s in strings:
    result += s

# GOOD — O(n) memory
result = "".join(strings)

# REQUIRED: io.StringIO for building strings
from io import StringIO

buffer = StringIO()
for item in items:
    buffer.write(f"{item}\n")
result = buffer.getvalue()
```

## Data Structure Selection

```python
# REQUIRED: right structure for memory efficiency
# Array of structs → list of dataclass
# BAD — dict overhead per item
users = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

# GOOD — dataclass with __slots__
@dataclass(slots=True)
class User:
    id: int
    name: str

users = [User(1, "Alice"), User(2, "Bob")]

# REQUIRED: array module for homogeneous numeric data
# BAD — list of ints (each int is a full Python object)
numbers = [1, 2, 3, 4, 5]  # ~140 bytes

# GOOD — array (compact C array)
from array import array
numbers = array("i", [1, 2, 3, 4, 5])  # ~20 bytes

# REQUIRED: bytearray for mutable bytes
# BAD — bytes are immutable, creates copies
data = b"hello"
data = data + b" world"  # creates new bytes object

# GOOD — bytearray is mutable
data = bytearray(b"hello")
data.extend(b" world")  # modifies in place
```

## Memory Profiling

```python
# REQUIRED: use profiler decorators
from cli.profiler import timed, track_memory, format_bytes

@track_memory("data_processor")
def process_large_dataset(data: bytes) -> dict:
    """Process large dataset — tracks memory allocation."""
    result = {}
    for chunk in chunked(data, 1024):
        result.update(parse_chunk(chunk))
    return result

# Check memory:
from cli.profiler import get_memory_stats
stats = get_memory_stats("data_processor")
print(stats[0])  # → current=12.3MB, peak=45.6MB, allocs=7

# REQUIRED: estimate object weight
from cli.profiler import object_weight, deep_weight

w = object_weight(large_dict)
print(f"Shallow weight: {format_bytes(w)}")

w = deep_weight(large_dict)
print(f"Deep weight: {format_bytes(w)}")
```

## Lazy Evaluation

```python
# REQUIRED: lazy module imports for optional dependencies
_numpy = None

def get_numpy():
    """Lazy import of numpy — only when needed."""
    global _numpy
    if _numpy is None:
        import numpy
        _numpy = numpy
    return _numpy

# REQUIRED: lazy file reading
def read_lines(path: str) -> Generator[str, None, None]:
    """Yield lines one at a time — never load entire file."""
    with open(path) as f:
        for line in f:
            yield line.rstrip("\n")

# REQUIRED: lazy property caching
class Data:
    @cached_property
    def expensive(self) -> list[int]:
        """Computed once, cached on instance."""
        return sorted(range(1000), reverse=True)
```

## Memory-Efficient Patterns

```python
# REQUIRED: bounded caches
from functools import lru_cache

@lru_cache(maxsize=256)  # bounded — won't grow forever
def cached_function(x: int) -> int:
    return x * x

# REQUIRED: delete references when done
large_data = load_huge_file()
process(large_data)
del large_data  # free memory immediately

# REQUIRED: use __del__ for cleanup (context manager preferred)
class Resource:
    def __init__(self):
        self._data = allocate_memory()

    def __del__(self):
        self._data = None  # hint to GC

# REQUIRED: context managers for resource lifecycle
class DatabaseConnection:
    def __enter__(self):
        self._conn = connect()
        return self._conn

    def __exit__(self, *exc):
        self._conn.close()
```

## Memory Monitoring

```python
# REQUIRED: check memory usage in production
import tracemalloc

def monitor_memory():
    """Snapshot memory usage."""
    tracemalloc.start()
    # ... do work ...
    current, peak = tracemalloc.get_traced_memory()
    print(f"Current: {current / 1024 / 1024:.1f}MB")
    print(f"Peak: {peak / 1024 / 1024:.1f}MB")
    tracemalloc.stop()

# REQUIRED: compare snapshots
def find_memory_leak():
    """Find what's using memory."""
    tracemalloc.start()
    snapshot1 = tracemalloc.take_snapshot()
    # ... run code ...
    snapshot2 = tracemalloc.take_snapshot()
    stats = snapshot2.compare_to(snapshot1, "lineno")
    for stat in stats[:10]:
        print(stat)
```

## Banned Memory Anti-patterns

- Classes without `__slots__`
- `import module` → `from module import name` (loads entire module)
- List comprehension for filtering → generator expression
- String concatenation in loops → `"".join()`
- Mutable default arguments → `None` + factory
- `isinstance(x, (A, B, C))` → `match/case` for 3+ branches
- Global mutable state → class with `__slots__`
- `print()` for logging → `logging.getLogger()`
- Hardcoded paths → `Path(__file__).parent / "data"`
- `import *` → explicit `from x import y`
