---
name: error_handling
description: Error handling patterns from CPython — exception hierarchy, chaining, context managers, cleanup. Activate when writing error-prone code or after catching exceptions.
---

# Error Handling — CPython Patterns

Professional exception handling from https://github.com/python/cpython.

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

class ConfigError(AppError):
    """Configuration error."""

# WHY: specific exceptions allow precise catching
try:
    process()
except ValidationError as e:
    handle_validation(e)
except DatabaseError as e:
    handle_db(e)
except AppError as e:
    handle_generic(e)  # catch-all for our exceptions
```

## Exception Chaining

```python
# REQUIRED: use `raise X from Y` to preserve cause
def load_config(path: str) -> Config:
    """Load config with proper exception chaining."""
    try:
        raw = Path(path).read_text()
    except FileNotFoundError as exc:
        raise ConfigError(f"Config not found: {path}") from exc
    try:
        return parse_config(raw)
    except ParseError as exc:
        raise ConfigError(f"Invalid config: {path}") from exc

# WHY: chains preserve the original traceback for debugging
```

## Context Managers for Cleanup

```python
# REQUIRED: contextlib for resource management
from contextlib import contextmanager, asynccontextmanager, suppress

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

@contextmanager
def atomic_write(path: str):
    """Write file atomically — roll back on error."""
    tmp = Path(path).with_suffix(".tmp")
    try:
        with open(tmp, "w") as f:
            yield f
        tmp.rename(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

# REQUIRED: suppress for ignoring expected exceptions
from contextlib import suppress

with suppress(FileNotFoundError):
    Path("temp.txt").unlink()

# WHY: cleaner than try/except/pass
```

## Safe Default Patterns

```python
# REQUIRED: sentinel for "no value" (CPython pattern)
_sentinel = object()

def get(key: str, default: object = _sentinel) -> str:
    """Get value. Distinguish 'None' from 'not provided'."""
    if default is _sentinel:
        raise KeyError(f"Key {key!r} not found")
    return _cache.get(key, default)

# REQUIRED: None + factory for mutable defaults
def process(items: list[int] | None = None) -> list[int]:
    """Process items with safe mutable default."""
    if items is None:
        items = []
    items.append(1)
    return items
```

## Exception Groups (Python 3.11+)

```python
# REQUIRED: except* for ExceptionGroup
async def fetch_all(urls: list[str]) -> list[bytes]:
    """Fetch all URLs, collect errors in group."""
    errors: list[Exception] = []
    results: list[bytes] = []

    for url in urls:
        try:
            result = await fetch(url)
            results.append(result)
        except FetchError as e:
            errors.append(e)

    if errors:
        raise ExceptionGroup("fetch failures", errors)
    return results

# Catch specific exception types from group
try:
    results = await fetch_all(urls)
except* FetchError as eg:
    for exc in eg.exceptions:
        log.warning("Fetch failed: %s", exc)
except* TimeoutError as eg:
    for exc in eg.exceptions:
        log.error("Timeout: %s", exc)
```

## Retry Patterns

```python
# REQUIRED: retry with backoff
import time
from typing import TypeVar

T = TypeVar("T")

def retry(
    func,
    max_attempts: int = 3,
    backoff: float = 1.0,
    exceptions: tuple = (Exception,),
) -> T:
    """Retry function with exponential backoff."""
    last_exc = None
    for attempt in range(max_attempts):
        try:
            return func()
        except exceptions as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                time.sleep(backoff * (2 ** attempt))
    raise last_exc  # type: ignore[misc]

# Usage:
result = retry(lambda: fetch_data(), max_attempts=3, exceptions=(IOError,))
```

## Logging Exceptions

```python
# REQUIRED: log with exc_info for full traceback
import logging

log = logging.getLogger(__name__)

def process_file(path: str) -> None:
    """Process file with proper exception logging."""
    try:
        data = parse(path)
    except ParseError:
        log.exception("Failed to parse %s", path)  # includes traceback
        raise
    except Exception:
        log.critical("Unexpected error processing %s", path, exc_info=True)
        raise
```

## Banned Anti-patterns

- Bare `except:` → `except Exception:` at minimum
- `except Exception: pass` → at least log it
- `raise Exception("msg")` → use specific exception type
- `try: ... except: ...` → catch specific exceptions
- Mutable default arguments → `None` + factory
- Global mutable state → class with `__slots__`
- `print()` for errors → `logging.exception()`
