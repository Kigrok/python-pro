---
name: api_design
description: API design patterns from CPython — naming, signatures, overloading, deprecation, backwards compatibility. Activate when designing public APIs or libraries.
---

# API Design — CPython Patterns

Professional API design from https://github.com/python/cpython.

## Naming Conventions

```python
# REQUIRED: PEP 8 naming
def process_data(items: list[str]) -> dict[str, int]:
    """Process items and return counts."""
    return {item: len(item) for item in items}

# REQUIRED: snake_case for functions and variables
def get_user(user_id: int) -> User: ...
def is_valid(data: dict) -> bool: ...
max_retries: int = 3

# REQUIRED: PascalCase for classes
class UserManager: ...
class DatabaseConnection: ...

# REQUIRED: UPPER_SNAKE_CASE for constants
MAX_RETRIES: int = 3
DEFAULT_TIMEOUT: float = 30.0

# REQUIRED: _prefix for private
def _validate_input(data: str) -> str: ...
class _InternalState: ...
```

## Function Signatures

```python
# REQUIRED: keyword-only arguments for clarity
def create_user(
    name: str,
    email: str,
    *,
    role: str = "user",
    active: bool = True,
) -> User:
    """Create user with explicit keyword args."""
    return User(name=name, email=email, role=role, active=active)

# Usage: create_user("Alice", "alice@example.com", role="admin")

# REQUIRED: positional-only for performance-critical (CPython pattern)
def add(a: int, b: int, /) -> int:
    """Add two numbers. Positional-only for speed."""
    return a + b

# add(1, 2) ✓
# add(a=1, b=2) ✗ — positional-only
```

## Overloading Patterns

```python
# REQUIRED: @singledispatch for type-based dispatch
from functools import singledispatch

@singledispatch
def process(data):
    raise TypeError(f"Unsupported type: {type(data)}")

@process.register(str)
def _(data: str) -> str:
    return data.upper()

@process.register(list)
def _(data: list) -> list:
    return [process(item) for item in data]

# REQUIRED: @overload for type checker hints
from typing import overload

@overload
def fetch(url: str) -> str: ...
@overload
def fetch(url: str, as_bytes: bool) -> bytes: ...

def fetch(url: str, as_bytes: bool = False) -> str | bytes:
    """Fetch URL content."""
    ...
```

## Deprecation Patterns

```python
# REQUIRED: warnings.warn for deprecation
import warnings

def old_function() -> None:
    """Old function — deprecated."""
    warnings.warn(
        "old_function is deprecated, use new_function instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return new_function()

# REQUIRED: __deprecated__ for classes (Python 3.13+)
class OldClass:
    __deprecated__ = "Use NewClass instead"
```

## Backwards Compatibility

```python
# REQUIRED: alias old names to new names
def new_name() -> None:
    """New name for the function."""
    ...

# Keep old name as alias
old_name = new_name

# REQUIRED: *args, **kwargs for forward compatibility
def process(data, *args, **kwargs):
    """Process data with future-proof signature."""
    ...

# WHY: allows adding new parameters without breaking existing code
```

## Factory Functions

```python
# REQUIRED: factory functions over complex constructors
def create_parser(description: str) -> ArgumentParser:
    """Create parser with standard options."""
    parser = ArgumentParser(description=description)
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser

# REQUIRED: module-level factories
def get_cache(maxsize: int = 128) -> LRUCache:
    """Create cache with standard settings."""
    return LRUCache(maxsize=maxsize)
```

## Protocol for Structural Subtyping

```python
# REQUIRED: Protocol for duck typing
from typing import Protocol

class Writable(Protocol):
    """Anything that can be written to."""
    def write(self, data: bytes) -> int: ...

class Readable(Protocol):
    """Anything that can be read from."""
    def read(self, n: int = -1) -> bytes: ...

# Works with any class that has write/read methods
def copy(src: Readable, dst: Writable) -> int:
    """Copy data from src to dst."""
    return dst.write(src.read())
```

## Banned Anti-patterns

- `import *` in public API → explicit imports
- Mutable default arguments → `None` + factory
- Bare `except:` → `except Exception:` at minimum
- `isinstance(x, (A, B, C))` → `match/case` for 3+ branches
- Hardcoded paths → `Path(__file__).parent / "data"`
- Global mutable state → class with `__slots__`
- `print()` for output → return values or logging
- `lambda` for complex logic → named function
