#!/usr/bin/env python3
# skills/modern_python.md — PEP 657/680/684/698/701/702: Modern Python.

# Modern Python — PEP 657, 680, 684, 698, 701, 702

## PEP 657: Fine Grained Error Locations (Python 3.11+)

```python
# Python 3.11+ shows exactly where in the expression the error occurred
data = {"key": {"nested": "value"}}
result = data["key"]["nested"]["deep"]  # Error on "deep"

# Traceback shows:
# result = data["key"]["nested"]["deep"]
#        ~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^
# IndexError: string index out of range
```

## PEP 680: tomllib (Python 3.11+)

```python
import tomllib

# Read TOML file
with open("config.toml", "rb") as f:
    config: dict = tomllib.load(f)

# Parse TOML string
config = tomllib.loads('''
[server]
host = "localhost"
port = 8080
''')
```

## PEP 684: Per-Interpreter GIL (Python 3.12+)

```python
import sys

# Check if free-threaded Python
if hasattr(sys, "_is_gil_enabled"):
    gil_enabled: bool = sys._is_gil_enabled()
    print(f"GIL enabled: {gil_enabled}")

# Use multiprocessing for CPU-bound tasks
from multiprocessing import Pool

def process_chunk(chunk: list[int]) -> int:
    return sum(chunk)

with Pool(4) as pool:
    results: list[int] = pool.map(process_chunk, chunks)
```

## PEP 698: Override Decorator (Python 3.12+)

```python
from typing import override

class Base:
    def method(self) -> str:
        return "base"

class Child(Base):
    @override
    def method(self) -> str:
        return "child"
```

## PEP 701: F-strings (Python 3.12+)

```python
# Basic f-strings
name: str = "Alice"
message: str = f"Hello, {name}!"

# Nested quotes (Python 3.12+)
message = f"Hello {"world"}"

# Debugging (= syntax, Python 3.8+)
print(f"{name=}, {age=}")

# Multi-line
message = f"""
Name: {name}
Age: {age}
"""
```

## PEP 702: Deprecated Decorator (Python 3.13+)

```python
from typing import deprecated

@deprecated("Use new_function instead")
def old_function() -> str:
    return "old"

def new_function() -> str:
    return "new"
```

## PEP 678: Exception Notes (Python 3.11+)

```python
try:
    process_data(data)
except ValueError as e:
    e.add_note(f"Processing file: {filename}")
    e.add_note(f"Data size: {len(data)} bytes")
    raise
```

## Best Practices

```python
# 1. Use type hints everywhere
def process(data: list[int]) -> dict[str, int]:
    return {"count": len(data)}

# 2. Use match/case for complex conditions
match command:
    case "start":
        start()
    case "stop":
        stop()

# 3. Use walrus operator for concise code
if data := fetch_data():
    process(data)

# 4. Use exception groups for multiple errors
try:
    raise ExceptionGroup("errors", [ValueError("a"), TypeError("b")])
except* ValueError as eg:
    print(f"Value errors: {eg.exceptions}")

# 5. Use f-strings for formatting
name = "Alice"
print(f"Hello, {name}!")
```
## Stdlib Idioms

### pathlib
- `pathlib.Path` for all filesystem work — not `os.path` string ops.
- `Path.read_text()` / `write_text()` / `read_bytes()` for one-shot I/O.
- `.parent` / `relative_to()` are lexical — call `.resolve()` first to follow symlinks/`..`.
- Derive paths with `.with_suffix()` / `.with_stem()` / `.with_name()`, not string edits.
- `sorted(path.glob(...))` — glob order is arbitrary.

### functools
- `@cache` for unbounded pure memoization; `@lru_cache(maxsize=N)` in long-running procs.
- Never cache impure / side-effecting / non-hashable-arg functions.
- Don't `@cache` instance methods (pins every instance alive) — use `@cached_property`
  (needs a writable `__dict__`, so not with bare `__slots__`).
- `@wraps(func)` on EVERY decorator wrapper (preserves name/doc/signature).
- `partial(f, x)` over a lambda for frozen arguments.
- `reduce(..., initial)` whenever the iterable may be empty.
