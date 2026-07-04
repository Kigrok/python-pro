---
name: cpython_patterns
description: Professional patterns from CPython internals — sentinel objects, __all__, module structure, private helpers, descriptor protocol, class design. Activate when writing library code or modules.
---

# CPython Patterns — Professional Python Architecture

Patterns extracted from https://github.com/python/cpython — the reference implementation.

## Module Structure (CPython Standard)

```python
#!/usr/bin/env python3
# module.py — One-line purpose statement.

"""Module docstring: what this module does.

Long description if needed.
"""

from __future__ import annotations

__all__ = ["PublicAPI1", "PublicAPI2"]  # REQUIRED: explicit public API

# ── stdlib imports ──────────────────────────────────────────────
import sys
from os import environ
from pathlib import Path

# ── third-party imports ─────────────────────────────────────────
from pydantic import BaseModel

# ── local imports ───────────────────────────────────────────────
from config import settings

# ── constants ───────────────────────────────────────────────────
_MAX_RETRIES: Final[int] = 3
_DEFAULT_TIMEOUT: Final[float] = 30.0

# ── module-level state ──────────────────────────────────────────
_cache: dict[str, object] = {}
_initialized: bool = False
```

## `__all__` — Explicit Public API

```python
# REQUIRED: every module should define __all__
__all__ = [
    "public_function",
    "PublicClass",
    "CONSTANT",
]

# This tells `from module import *` what to export
# And helps linters detect unused imports
```

## Sentinel Objects

```python
# REQUIRED: use sentinel for "no value" (CPython pattern)
_sentinel = object()  # unique, never equal to anything

def get_value(key: str, default: object = _sentinel) -> str:
    """Get value or default. Distinguish 'None' from 'not provided'."""
    if default is _sentinel:
        raise KeyError(f"Key {key!r} not found and no default provided")
    return _cache.get(key, default)

# CPython uses this pattern extensively:
# - functools._initial_missing
# - inspect._empty
# - typing._NoDefault
```

## Private Helper Functions

```python
# REQUIRED: underscore prefix for internal helpers
def public_api(arg: str) -> Result:
    """Public function with clean interface."""
    validated = _validate_input(arg)
    processed = _process(validated)
    return _format_result(processed)

def _validate_input(arg: str) -> str:
    """Internal: validate and sanitize input."""
    ...

def _process(data: str) -> bytes:
    """Internal: core processing logic."""
    ...

def _format_result(data: bytes) -> Result:
    """Internal: format output."""
    ...

# CPython uses this pattern:
# - public function → _private implementation
# - Keeps API surface minimal
# - Internal functions can change without breaking API
```

## Class Design (CPython Style)

```python
from dataclasses import dataclass, field
from typing import ClassVar

# REQUIRED: __slots__ on all classes
class Point:
    """A 2D point."""
    __slots__ = ("x", "y")

    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y

    def __repr__(self) -> str:
        return f"Point(x={self.x!r}, y={self.y!r})"

# REQUIRED: dataclass(slots=True) for data carriers
@dataclass(slots=True)
class CacheInfo:
    """Cache statistics."""
    hits: int = 0
    misses: int = 0
    maxsize: int = 0
    currsize: int = 0

# REQUIRED: ClassVar for class-level constants
class Config:
    """Configuration with class-level constants."""
    MAX_SIZE: ClassVar[int] = 100
    DEFAULT_TIMEOUT: ClassVar[float] = 30.0

    def __init__(self, host: str) -> None:
        self.host = host
```

## Descriptor Protocol

```python
# REQUIRED: use descriptors for computed attributes (CPython pattern)
class cached_property:
    """Cache a property result as instance attribute."""
    __slots__ = ("func", "attrname")

    def __init__(self, func):
        self.func = func
        self.attrname = None

    def __set_name__(self, owner, name):
        self.attrname = name

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        val = self.func(instance)
        instance.__dict__[self.attrname] = val
        return val

# Usage:
class Data:
    @cached_property
    def expensive(self) -> list[int]:
        """Computed once, cached on instance."""
        return sorted(range(1000), reverse=True)
```

## Exception Hierarchy

```python
# REQUIRED: specific exception hierarchy (CPython pattern)
class AppError(Exception):
    """Base exception for application."""

class ValidationError(AppError):
    """Input validation failed."""

class NotFoundError(AppError):
    """Resource not found."""

class DatabaseError(AppError):
    """Database operation failed."""

# REQUIRED: exception chaining
def process(file_path: str) -> None:
    """Process file with proper exception chaining."""
    try:
        data = parse(file_path)
    except ParseError as exc:
        raise ValidationError(f"Bad input: {file_path}") from exc

# REQUIRED: except* for ExceptionGroup (Python 3.11+)
try:
    results = await gather(*tasks)
except* ValidationError as eg:
    for exc in eg.exceptions:
        log.warning("Validation failed: %s", exc)
except* DatabaseError as eg:
    for exc in eg.exceptions:
        log.error("DB error: %s", exc)
```

## Context Managers

```python
# REQUIRED: contextlib for resource management
from contextlib import contextmanager, asynccontextmanager

@contextmanager
def timer(label: str):
    """Measure execution time."""
    import time
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        print(f"{label}: {elapsed:.3f}s")

# Usage:
with timer("process"):
    process_data()

# REQUIRED: async context managers
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
```

## Factory Functions

```python
# REQUIRED: factory functions over complex constructors (CPython pattern)
def create_parser(description: str) -> ArgumentParser:
    """Create argument parser with standard options."""
    parser = ArgumentParser(description=description)
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--config", type=Path)
    return parser

# REQUIRED: module-level factory functions
def get_cache(maxsize: int = 128) -> LRUCache:
    """Create cache with standard settings."""
    return LRUCache(maxsize=maxsize)

# Usage:
cache = get_cache(maxsize=256)
```

## State Machines

```python
# REQUIRED: enum for state machines (CPython pattern)
from enum import Enum, auto

class ConnectionState(Enum):
    """Connection states."""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    ERROR = auto()

    @property
    def is_active(self) -> bool:
        """Check if state is active."""
        return self in (self.CONNECTING, self.CONNECTED)

# REQUIRED: match/case for state dispatch
def handle_state(state: ConnectionState) -> None:
    """Handle connection state change."""
    match state:
        case ConnectionState.DISCONNECTED:
            init_connection()
        case ConnectionState.CONNECTING:
            wait_for_handshake()
        case ConnectionState.CONNECTED:
            process_messages()
        case ConnectionState.ERROR:
            reconnect()
```

## Type Patterns

```python
# REQUIRED: TypeAlias for complex types (CPython pattern)
from typing import TypeAlias

JSONScalar = str | int | float | bool | None
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
JSONDict = dict[str, JSONValue]

# REQUIRED: Protocol for structural subtyping
from typing import Protocol

class Writable(Protocol):
    """Anything that can be written to."""
    def write(self, data: bytes) -> int: ...

class Readable(Protocol):
    """Anything that can be read from."""
    def read(self, n: int = -1) -> bytes: ...

# REQUIRED: Literal for constrained types
from typing import Literal

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
Method = Literal["GET", "POST", "PUT", "DELETE", "PATCH"]
```

## Module-Level Patterns

```python
# REQUIRED: __init_subclass__ for registration (CPython pattern)
class Plugin:
    """Base plugin class."""
    _registry: ClassVar[dict[str, type["Plugin"]]] = {}

    def __init_subclass__(cls, name: str = "", **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if name:
            cls._registry[name] = cls

class JsonPlugin(Plugin, name="json"):
    """JSON serialization plugin."""
    ...

class XmlPlugin(Plugin, name="xml"):
    """XML serialization plugin."""
    ...

# REQUIRED: __class_getitem__ for generic subscripting
class Cache:
    """Generic cache."""
    def __class_getitem__(cls, item):
        return type(f"Cache[{item.__name__}]", (cls,), {"_type": item})
```

## Banned Anti-patterns

- `lambda x: ...` → named function with docstring
- Bare `except:` → `except Exception:` at minimum
- `isinstance(x, (A, B, C))` → `match/case` for 3+ branches
- Mutable default arguments → `None` + factory
- Global mutable state → class with `__slots__`
- `print()` for logging → `logging.getLogger()`
- Hardcoded paths → `Path(__file__).parent / "data"`
- `import *` → explicit `from x import y`
