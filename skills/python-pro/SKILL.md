---
name: python-pro
description: Production Python 3.11+ standard — strict typing (no Any/Optional), __slots__ on every class, exact-name imports, match/case over if-elif, async-first I/O, Decimal for money, ClassVar constants, security hygiene (no eval/exec/shell=True). Use BEFORE writing or reviewing any .py file, requirements.txt, ruff.toml, mypy.ini, or pytest.ini.
---

# Python Pro — Global Rules

Production Python 3.11+ standard. ACTIVATE on any .py file. Apply BEFORE writing code.

## Prime Directives

Every decision optimises these nine axes. When two conflict, prefer the earlier one —
but NEVER trade away correctness or safety for any of them.

1. **Simpler is better.** Fewest moving parts, least nesting, no cleverness. If it is hard
   to explain, redesign it. → flat over nested, guard clauses, one task per function,
   EAFP, `match/case`, delete before adding.
2. **Faster is better.** Lowest-complexity algorithm and the right data structure; `set`/
   `dict` for lookups (O(1)), comprehensions/generators over manual loops, no repeated
   work in hot paths, cache pure functions.
3. **Fewer machine resources is better.** No redundant I/O, queries, or allocations; reuse
   clients/sessions/pools; stream instead of buffering; async for I/O-bound work; batch.
4. **Smaller code is better.** Stdlib over a dependency; DRY; inline single-use vars; no
   dead code; less surface = less to break.
5. **Less memory is better.** `__slots__` / `dataclass(slots=True)`, generators over lists,
   `tuple`/`frozenset` for constants, iterate don't materialise, bounded caches.
6. **Safer is better.** No `eval`/`exec`/`shell=True`, parameterised SQL, `secrets` for
   tokens, validate input at the boundary, narrow exceptions, no untrusted deserialisation.
7. **More precise typing is better.** Annotate everything; no `Any`/`Optional`; concrete
   containers; `Protocol`/`TypeVar`/`Self`/`Literal` over loose types; pass strict mypy.
8. **Tighter docs are better.** One-line imperative docstring on public API only; comments
   say WHY, never paraphrase code; delete the obvious.
9. **Lower-level is better.** Stdlib > PyPI; primitives > frameworks; direct > abstracted.
   Fewer dependencies = less to break, audit, update. Only add a lib when stdlib genuinely
   can't do it or doing it manually is complex (crypto, parsing). Check `cli/deps.py`.

Every rule below is one of these directives made concrete.

## BANNED — Never Do This

```python
# BANNED: Any type — use Union instead
```python
# BAD — Any type
x: object = get_something()

# GOOD — precise type
x: str = get_something()

# Or when genuinely opaque
result: dict[str, object] = some_function()
```

# BANNED: Optional — use Union with None
```python
# BAD
y: str | None = None  # WRONG

# GOOD
y: str | None = None
```

# BANNED: import x — ALWAYS use from x import y
import json  # WRONG
import asyncio  # WRONG
import os  # WRONG
import httpx  # WRONG — never import full third-party modules
import aiohttp  # WRONG
import fastapi  # WRONG

# GOOD — exact name binding
from json import loads, dumps
from asyncio import run, gather
from os import environ
from httpx import AsyncClient, Client  # only what you need
from aiohttp import ClientSession, ClientTimeout
from fastapi import APIRouter, Depends

# BANNED: inline imports — ALL imports at top of file
def foo():
    import json  # WRONG
    json.loads(x)

# GOOD: ALL imports at top
from json import loads

def foo():
    loads(x)

# BANNED: functions with multiple tasks
def process(user):
    validate(user)
    save(user)
    send_email(user)

# BANNED: unused variables
result = compute(x)
return other_thing

# BANNED: comments paraphrasing code
x = compute()  # compute x

# AVOID: long value-dispatch if/elif chains (3+ branches) — use match/case
if cmd == "start":
    start()
elif cmd == "stop":
    stop()
elif cmd == "pause":
    pause()
```

## REQUIRED — Always Do This

```python
# REQUIRED: shebang + path comment
#!/usr/bin/env python3
# module.py — description.

# REQUIRED: ALL imports at top of file, exact-name only
# NEVER: import json, import httpx, import fastapi
# ALWAYS: from json import loads, from httpx import AsyncClient
from __future__ import annotations

from asyncio import run
from json import loads
from os import environ

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from config import settings
from core.database import get_db

logger: Logger = getLogger(__name__)
router: APIRouter = APIRouter()

# REQUIRED: type annotations on EVERYTHING
x: int = 1
name: str = "foo"
items: list[str] = []

# REQUIRED: use type() if you don't know the type
result = some_function()
print(type(result))  # Use this to determine type
result: dict[str, object] = some_function()  # then annotate precisely
class Foo:
    """One line."""
    def bar(self) -> None:
        """One line."""

# REQUIRED: __slots__ on ALL classes
class Foo:
    __slots__ = ("x",)

# REQUIRED: constants in classes
class Config:
    MAX_SIZE: ClassVar[int] = 100
    VK_URL: ClassVar[str] = "https://..."

# REQUIRED: exact-name imports
from json import loads
from asyncio import run
from os import environ

# REQUIRED: one function = one task
def process_user(user: User) -> None:
    _validate(user)
    _save(user)
    _notify(user)

# REQUIRED: inline single-use variables
return compute(x)  # not: result = compute(x); return result
```

## Automatic Skill Detection

Skills are auto-detected by hook — AI doesn't need to figure out file paths.

| Pattern | Skill | Rules |
|---------|-------|-------|
| `async def`, `await`, `asyncio` | async | TaskGroup, Semaphore, gather, timeout |
| `aiohttp`, `httpx`, `ClientSession` | http | Connection pooling, timeouts, streaming |
| `sqlalchemy`, `asyncpg`, `session` | database | Query optimization, N+1, injection prevention |
| `class.*Protocol`, `class.*Factory` | patterns | Design patterns, algorithms |
| `import logging`, `getLogger`, `logger.` | logging | Module logger, lazy `%` args, no `print`, NullHandler |
| `eval`, `subprocess`, `pickle`, `yaml.load` | security | No eval/exec, no `shell=True`, safe deser, `secrets` |

Hook runs automatically and provides:
- File paths (detected via git diff)
- Active skills (detected via code patterns)
- Lint results (auto-fixed + remaining errors)

AI receives ready-to-use report without spending tokens on file detection.

## Ignored Paths (NEVER touch)

- `venv/`, `.venv/`, `env/`, `.env/`
- `site-packages/`, `__pycache__/`, `*.pyc`
- `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`
- `node_modules/`, `dist/`, `build/`, `*.egg-info/`, `.git/`

## File Path — Use __file__, Never Hardcode

```python
# bad — hardcoded path
PATH = Path("/home/user/project/file.py")

# good — dynamic path from __file__
PATH = Path(__file__).parent / "data.json"
CONFIG_DIR = Path(__file__).parent.parent / "config"
```

Every file MUST start with shebang, then path comment.

```python
#!/usr/bin/env python3
# core/cache.py — Two-layer TTL cache with Redis fallback.

from __future__ import annotations
```

## House Stack

- HTTP: `aiohttp` or `httpx` — match project.
- Web API: `FastAPI` + `uvicorn`.
- ORM: `SQLAlchemy 2 async` + `asyncpg`.
- Telegram bots: `aiogram 3`.
- Money/prices: `Decimal` ALWAYS.
- Tests: `pytest` + `pytest-asyncio`.

The House Stack libraries are *sanctioned exceptions* — reach for them only when the
standard library genuinely can't do the job (see Dependencies below).

## Dependencies — Standard Library First

Default to Python's standard library. Add a third-party dependency ONLY when stdlib
cannot reasonably do the job; when you must, prefer a House Stack library and justify it.

### Prefer stdlib over these (common offenders)

- `requests` -> `urllib.request` / `http.client`; async at scale -> `httpx`/`aiohttp`.
- `pytz` -> `zoneinfo` (3.9+).
- `toml` (reading) -> `tomllib` (3.11+).
- `simplejson` / `ujson` -> `json`.
- `python-dateutil` (simple parse/format) -> `datetime`.
- `six`, `pathlib2` -> drop (Python 3 / `pathlib`).
- `mock` -> `unittest.mock`.
- `attrs` (simple records) -> `dataclasses`.
- small CLIs -> `argparse`, not `click`/`typer`.
- pure-function cache -> `functools.lru_cache`; pools -> `concurrent.futures`.
- hashing / ids / secrets -> `hashlib` / `uuid` / `secrets`.

### Genuinely needs third-party (stdlib insufficient -> allowed)

- Async HTTP at scale -> `httpx`/`aiohttp`; Web API -> `FastAPI`; ORM -> `SQLAlchemy` + `asyncpg`.
- Validation/settings -> `pydantic`; YAML -> `pyyaml` (no stdlib YAML); Telegram -> `aiogram`.

### Choosing a third-party library — secure, low-level, fast, async

When stdlib won't do, pick the dependency that is, in priority order: **secure** (audited,
actively maintained, minimal attack surface, no unsafe deserialization), **async-native**
(not a sync API wrapped in threads), **low-level / fast** (C/Rust-backed, minimal
overhead), and **lean** (few transitive deps). Concretely:

- DB drivers: `asyncpg` (Postgres), `asyncmy`/`aiomysql` (MySQL), `motor` (Mongo) — async, low-level. NOT sync `psycopg2` / `pymysql` / `pymongo`.
- HTTP: `aiohttp` / `httpx` (async); event loop -> `uvloop` (libuv, fast). NOT `requests` / `flask`.
- Serialisation & validation in hot paths: `orjson` / `msgspec` (Rust/C, fast, safe), `pydantic` v2 (Rust core). NOT `pickle` (insecure) or `marshmallow` (slower).
- Crypto: `cryptography` (OpenSSL-backed, audited) or `PyNaCl` (libsodium). Never hand-rolled.
- Pin every dependency in `requirements.txt`; avoid abandoned or transitive-heavy packages.

Rule of thumb: if it's one stdlib import away, don't add a package. Run the `check_stdlib`
MCP tool to catch gratuitous dependencies.

## Imports

### Exact-name binding (stdlib included)

```python
# bad
import asyncio
asyncio.run(main())

# good
from asyncio import run
run(main())
```

### ALL imports at the top — NO inline imports

```python
# bad
def foo():
    import json
    json.loads(x)

# good
from json import loads

def foo():
    loads(x)
```

### Relative imports in __init__.py

```python
# __init__.py
from .module import Class
__all__ = ["Class"]
```

## Annotations — ALL of them (NON-NEGOTIABLE)

**EVERY variable, parameter, class attribute, constant, return type — mandatory. NO EXCEPTIONS.**

```python
# bad
def foo(x):
    y = x + 1
    return y

# good
def foo(x: int) -> int:
    y: int = x + 1
    return y

# bad — class attributes without annotations
class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_id", "id"),)

# good — explicit annotations
class User(Base):
    __tablename__: str = "users"
    __table_args__: tuple = (Index("ix_id", "id"),)

# bad — enum values without annotations
class Status(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"

# good — explicit annotations
class Status(StrEnum):
    ACTIVE: str = "active"
    INACTIVE: str = "inactive"
```

## Banned types

`Any` and `Optional` are BANNED.

```python
# bad
x: object = get_something()
y: str | None = None

# good
x: str = get_something()
y: str | None = None  # None: lazy init
```

## Docstrings — PEP 257, PUBLIC API only

A one-line imperative summary on **public** classes and functions (name not
`_`-prefixed). A multi-line docstring is fine for complex public functions (PEP 257):
summary line, blank line, then the details / Args / Returns / Raises. Private
`_helpers` and dunder methods take **no** docstring — a non-obvious one-line `# WHY`
comment instead. Never prose that merely paraphrases the code. The validator flags a
missing public docstring as a **warning**, never an error.

```python
# bad — paraphrase prose, and a docstring on a private helper
class Foo:
    """This class is a foo that does foo things and also bar things."""

    def _bar(self) -> None:
        """Bar the foo."""

# good — public gets one line, private gets none
class Cache:
    """Two-layer TTL cache with Redis fallback."""

    def get(self, key: str) -> bytes | None:
        """Fetch a value from cache or Redis."""

    def _evict(self) -> None:  # WHY: LRU, drop coldest 10% when full
        ...
```

## __slots__ — MANDATORY for ALL classes

```python
# bad
class Foo:
    def __init__(self):
        self.x = 1

# good
class Foo:
    __slots__ = ("x",)

    def __init__(self) -> None:
        self.x: int = 1
```

## Constants — module-level UPPER_CASE or a class with ClassVar

Module-level `UPPER_CASE` constants (optionally `Final`) are idiomatic (PEP 8). Group
**related** config into a class with `ClassVar` when cohesion helps.

```python
# fine — simple module-level constants
MAX_SIZE: Final[int] = 100
API_TIMEOUT: Final[float] = 30.0

# also good — related config grouped in a class
class VKConfig:
    """VK OAuth configuration."""
    AUTHORIZE: ClassVar[str] = "https://oauth.vk.com/authorize"
    TOKEN_URL: ClassVar[str] = "https://oauth.vk.com/access_token"
    API_URL: ClassVar[str] = "https://api.vk.com/method/users.get"
    VERSION: ClassVar[str] = "5.131"

# also good — dataclass for structured data
@dataclass(slots=True)
class Endpoint:
    """API endpoint configuration."""
    url: str
    method: str = "GET"
    timeout: float = 30.0
```

## match/case — for multi-way dispatch

Prefer `match/case` for value-dispatch of **3+ branches**; a one- or two-branch
`if/elif` is fine. **NESTED match/case BANNED** — extract checks into separate functions.

```python
# BANNED: nested match/case
match x:
    case "a":
        match y:
            case 1:
                do_something()

# GOOD: extract to separate function
def handle_a(y: int) -> None:
    """Handle case 'a'."""
    match y:
        case 1:
            do_something()

match x:
    case "a":
        handle_a(y)
```

## Data structure optimization

- Immutable constants → `tuple`, `frozenset`
- Frequent lookups → `dict` (O(1))
- Membership checks → `set` (O(1))

## Default values for safety

```python
# bad — crashes if key missing
user_id: int = payload["sub"]

# good — safe default
user_id: int = int(payload.get("sub", 0))
```

## Functions — module-level or grouped, by cohesion

Module-level functions are fine for stateless utilities and entry points (PEP 8 /
Google style — "import modules, not functions" applies to imports, not to where you
define them). Group related helpers into a namespace class when they share state or
read better together. Classes are for state and behaviour, not as a mandatory wrapper.

## Line length

88 characters max. Wrap long strings and expressions.

## Explicit Arguments — Always Specify

EVERY argument must be explicit, not inferred. Especially for DB models, APIs, configs.

```python
# bad — column name inferred from variable
class User(Base):
    name = Column(String)

# good — explicit column name and params
class User(Base):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="User display name",
    )

# bad — config without explicit keys
config = {"host": "localhost", "port": 5432}

# good — explicit TypedDict or dataclass
@dataclass(slots=True)
class DBConfig:
    host: str = "localhost"
    port: int = 5432
    name: str = "app_db"
```

### ALL Variables Must Have Annotations

EVERY variable, constant, class attribute — mandatory annotation.

```python
# bad
_MAX_SIZE = 100
result = compute(x)
names = ["alice", "bob"]

# good
_MAX_SIZE: int = 100
result: dict[str, int] = compute(x)
names: list[str] = ["alice", "bob"]

# bad — class attributes without types
class Config:
    DEBUG = True
    PORT = 8000

# good
class Config:
    DEBUG: ClassVar[bool] = True
    PORT: ClassVar[int] = 8000
```

### SQLAlchemy Models — Full Specification

```python
from sqlalchemy import String, Integer, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

class User(Base):
    """Application users table."""
    __tablename__ = "users"
    __table_args__ = {"comment": "Application users"}

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True,
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Display name",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )
    keys: Mapped[list["Key"]] = relationship(
        back_populates="user", lazy="selectin",
    )
```

### Pydantic Models — Full Specification

```python
from pydantic import BaseModel, Field

class UserResponse(BaseModel):
    """User API response schema."""
    id: int = Field(..., description="User ID")
    email: str = Field(..., description="Email address")
    name: str = Field(..., min_length=1, max_length=100)
    is_active: bool = Field(default=True, description="Account status")
```

## Single Responsibility per Function

Each function does ONE logical task. Split complex functions into smaller ones.

```python
# bad — multiple tasks in one function
def process_user(user):
    validate(user)
    save_to_db(user)
    send_email(user)
    log_action(user)

# good — one task per function, orchestrator calls them
def process_user(user: User) -> None:
    """Orchestrate user processing pipeline."""
    _validate_user(user)
    _save_user(user)
    _notify_user(user)
    _log_user_action(user)

def _validate_user(user: User) -> None:
    """Validate user data."""

def _save_user(user: User) -> None:
    """Persist user to database."""

def _notify_user(user: User) -> None:
    """Send notification email."""

def _log_user_action(user: User) -> None:
    """Log user action for audit."""
```

## DRY

Two identical constructor calls → helper/factory/loop. A function body that repeats
another by ≥ 50% → extract one shared, parameterised helper.

## Sorting — Always Extract

Extract sort-key lambdas into named functions for reuse and readability.

## No Unused Variables

If a variable is used only once — inline it. Don't create variables for one-time use.

```python
# BAD — variable used once
result = compute(x)
return result

# GOOD — inline
return compute(x)

# BAD — temp variable
temp = get_user(id)
name = temp.name

# GOOD — direct
name = get_user(id).name
```

Exception: variables that improve readability in complex expressions.

## Decorators — Use for Cross-Cutting Concerns

Decorators for cross-cutting concerns: error handling, timing, health checks, caching.
Always `@wraps(func)`. Vary the one pattern below for timing/health-check.

```python
from functools import wraps

def handle_errors(func: Callable) -> Callable:
    @wraps(func)
    async def wrapper(*args: object, **kwargs: object) -> object:
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            logger.error("%s failed: %s", func.__name__, exc)
            raise
    return wrapper
```

## Cache — lru_cache for Pure Functions

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def compute(x: int) -> int:
    return x * x

# For async — use custom cache or cachetools
from cachetools import TTLCache

cache: TTLCache = TTLCache(maxsize=100, ttl=60)
```

## Security

- `eval`/`exec` BANNED on user input
- `subprocess` → never `shell=True`
- SQL → parameterized queries only
- Secrets → env/vault, never in code
- `pickle`/`marshal` → only on trusted source
- `secrets` (not `random`) for tokens; `hashlib.sha256`+ (never `md5`/`sha1`) for security
- `tempfile.mkstemp` (never `mktemp`); never `verify=False` on TLS in production
- `assert` is NOT validation — `-O` strips it; raise an explicit exception

## Enforced Idioms (validator)

The AST validator flags these directly:
- `is None` / `is not None` — never `== None` / `!= None`.
- Test booleans directly — never `== True` / `== False`.
- No mutable default args (`def f(x=[])`) — use `None` + in-body init.
- No bare `except:` — catch a specific type.
- No wildcard `from x import *`.
- `Any` / `Optional` BANNED in annotations — use a precise type or `X | None`.
- Functions over 60 statements — split into single-purpose helpers.
- A function body that duplicates an earlier one — unify into a shared helper.
- No `except Exception` / `except BaseException` as a catch-all (ok only to log + re-raise).
- No `assert` outside tests — `-O` strips it; raise `ValueError`/`TypeError`.
- `raise X` inside `except` must be `raise X from exc` (preserve the chain).

The deterministic pipeline (hook + `fix_file`) also runs, with NO AI: a security AST
scan (eval/exec/shell/pickle/secrets/weak-hash), a cyclomatic-complexity gate (CC > 10),
a stdlib-first dependency scan (flags third-party replaceable by stdlib / a safer async
lib), and a semantic AST-hash cache that skips re-checking unchanged clean files.

## More Global Rules

- EAFP over LBYL; errors never pass silently (log or `raise`, never swallow).
- `except Exception` only to log and re-raise; never catch the `BaseException` family.
- Flat over nested: guard clauses, not pyramids.
- Logging, not `print`: `logger = getLogger(__name__)`, lazy `%` args, `logger.exception`
  only inside an `except` block.
- `pathlib` over `os.path`; `@wraps` on every decorator; `functools.cache` only on pure
  functions.
- match/case: dotted constants only (a bare name captures); wildcard `case _:` last.
- One function = one logical action: if it decomposes into separate steps, split it
  (the validator flags functions over ~60 statements).
- DRY hard: a function body that repeats another (≥ ~50%) is unified into a shared helper
  (validator flags exact duplicates; pylint R0801 catches cross-file near-dups).
- Test every public function against its standard failure modes: empty / None /
  wrong-type / boundary inputs, and each exception it can raise (`pytest.raises`).
- Large or repeated type annotations → factor into a `type` alias or a generic
  (`def f[T]`, `TypeVar`) instead of inlining a big nested type on one function.

## Domain Rule Sheets

Auto-loaded by code pattern (see the detection table above). Authoritative detail lives
in `skills/`: `style`, `typing`, `async`, `control_flow`, `data_structures`,
`modern_python`, `patterns`, `errors`, `logging`, `security`, `dependencies`,
`database`, `http`, `fastapi`, `pydantic`, `testing`.
