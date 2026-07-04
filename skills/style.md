#!/usr/bin/env python3
# skills/style.md — PEP 8/257/701: Code Style & Formatting.

# Python Style — PEP 8, PEP 257, PEP 701

## PEP 8: Style Guide

### Naming Conventions

```python
# Functions/variables: snake_case
def calculate_total() -> float:
    total_price: float = 0.0

# Classes: PascalCase
class UserProfile:
    pass

# Constants: UPPER_SNAKE_CASE
MAX_RETRIES: Final[int] = 3
API_TIMEOUT: Final[float] = 30.0

# Private: leading underscore
def _internal_helper() -> None:
    pass
```

### Imports (PEP 328)

```python
# 1. Standard library
from asyncio import run
from json import loads

# 2. Third party
from fastapi import APIRouter

# 3. Local
from config import settings

# ALWAYS exact-name binding
from json import loads, dumps  # GOOD
import json  # BAD
```

### Whitespace & Line Length

```python
# 88 chars max (modern projects)
# 2 blank lines before top-level, 1 between methods

def long_function(
    var_one: str,
    var_two: str,
    var_three: str,
) -> None:
    if var_one == "a" and var_two == "b":
        if var_three == "c":
            do_something()
```

## PEP 257: Docstrings

```python
# One-line docstrings
def add(a: int, b: int) -> int:
    """Return the sum of two numbers."""
    return a + b

# Multi-line docstrings
def process(data: list[int]) -> dict[str, int]:
    """Process data and return statistics.

    Args:
        data: List of integers to process.
        threshold: Minimum value to include.

    Returns:
        Dictionary with 'count', 'sum', and 'average' keys.
    """
    filtered = [x for x in data if x >= 0]
    return {
        "count": len(filtered),
        "sum": sum(filtered),
        "average": sum(filtered) / len(filtered) if filtered else 0,
    }

# Class docstrings
class Cache:
    """In-memory cache with TTL support."""
    pass
```

### Docstring Rules

1. Use triple double quotes: `"""`
2. Start with verb in imperative mood: "Return", "Compute"
3. Don't restate the obvious
4. Include Args/Returns for complex functions

## Comparisons & Idioms

- `is None` / `is not None` — NEVER `== None` / `!= None` (`__eq__` can lie).
- Test booleans directly: `if flag:` / `if not flag:` — never `== True` / `== False`.
- Emptiness via truthiness: `if not seq:` / `if seq:` — not `len(seq) == 0`.
- Iterate directly: `for x in items:` — never `for i in range(len(items))`.
- Iterate a dict directly: `for key in d:` — not `for key in d.keys()`.

## Formatting (Black / PEP 8)

- Wrap inside `()` `[]` `{}` — never backslash line continuation.
- Break BEFORE binary operators when splitting multi-line expressions.
- Double quotes for strings; one statement per line; no `;`.
- Magic trailing comma = "keep exploded" — add it deliberately, never by accident.
- 2 blank lines around top-level defs, 1 between methods.
- No extraneous whitespace inside brackets or before `,` / `:` / call-`(`.

## Naming

- Classes `CapWords`; exceptions `CapWords` + `Error` suffix.
- Functions/vars `snake_case`; constants `UPPER_SNAKE`; never `mixedCase`.
- Never `l` / `O` / `I` as single-char names (look like `1` / `0`).
- Acronyms stay fully capped: `HTTPClient`, not `HttpClient`.

## Imports (grouping)

- Three groups, blank-line separated: stdlib → third-party → local.
- No wildcard `from x import *`.
- `from __future__` first; module dunders (`__all__`) after the docstring, before imports.
