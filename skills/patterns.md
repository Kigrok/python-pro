#!/usr/bin/env python3
# skills/patterns.md — Design Patterns and Algorithms.

# Python Patterns — Design Patterns & Algorithms

## Creational Patterns

### Factory

```python
from typing import Protocol

class UserFactory:
    @staticmethod
    def create(platform: str, data: dict) -> User:
        match platform:
            case "telegram":
                return TelegramUser(**data)
            case "vk":
                return VKUser(**data)
            case _:
                raise ValueError(f"Unknown platform: {platform}")
```

### Builder

```python
from typing import Self

class QueryBuilder:
    def __init__(self) -> None:
        self._filters: list[str] = []
        self._limit: int = 100

    def where(self, condition: str) -> Self:
        self._filters.append(condition)
        return self

    def limit(self, n: int) -> Self:
        self._limit = n
        return self

    def build(self) -> str:
        query = "SELECT * FROM users"
        if self._filters:
            query += " WHERE " + " AND ".join(self._filters)
        query += f" LIMIT {self._limit}"
        return query
```

### Singleton

```python
class Database:
    _instance: Database | None = None

    def __new__(cls) -> Database:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
```

## Structural Patterns

### Adapter

```python
class OldAPI:
    def get_data(self) -> bytes:
        return b"raw data"

class NewAPI:
    def fetch(self) -> dict:
        return {"key": "value"}

class APIAdapter:
    def __init__(self, old_api: OldAPI) -> None:
        self._api = old_api

    def fetch(self) -> dict:
        raw = self._api.get_data()
        return {"key": raw.decode()}
```

### Decorator

```python
from functools import wraps
from time import time

def cache(ttl: int = 60) -> Callable:
    def decorator(func: Callable) -> Callable:
        store: dict[str, tuple[object, float]] = {}

        @wraps(func)
        async def wrapper(*args: object) -> object:
            key = str(args)
            if key in store:
                value, ts = store[key]
                if time() - ts < ttl:
                    return value
            result = await func(*args)
            store[key] = (result, time())
            return result

        return wrapper
    return decorator
```

### Proxy

```python
class CachedUserRepo:
    def __init__(self, repo: UserRepo, cache: TTLCache) -> None:
        self._repo = repo
        self._cache = cache

    async def get(self, user_id: int) -> User | None:
        cached = await self._cache.get(f"user:{user_id}")
        if cached:
            return User(**cached)
        user = await self._repo.get(user_id)
        if user:
            await self._cache.set(f"user:{user_id}", user.dict())
        return user
```

## Behavioral Patterns

### Strategy

```python
from typing import Protocol

class PricingStrategy(Protocol):
    def calculate(self, base: Decimal, qty: int) -> Decimal: ...

class FixedPricing:
    def calculate(self, base: Decimal, qty: int) -> Decimal:
        return base * qty

class BulkPricing:
    def calculate(self, base: Decimal, qty: int) -> Decimal:
        discount = Decimal("0.9") if qty > 100 else Decimal("1")
        return base * qty * discount
```

### Observer

```python
class EventEmitter:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = {}

    def on(self, event: str, handler: Callable) -> None:
        self._handlers.setdefault(event, []).append(handler)

    async def emit(self, event: str, data: object) -> None:
        for handler in self._handlers.get(event, []):
            await handler(data)
```

### State

```python
from typing import Protocol

class OrderState(Protocol):
    async def next(self, order: Order) -> OrderState: ...

class PendingState:
    async def next(self, order: Order) -> OrderState:
        order.status = "processing"
        return ProcessingState()

class ProcessingState:
    async def next(self, order: Order) -> OrderState:
        order.status = "completed"
        return CompletedState()
```

## Principles (Zen / Google style)

- EAFP over LBYL; errors never pass silently (log or raise — silence must be explicit).
- Duck-typing / Protocols over `isinstance()` chains for polymorphic dispatch.
- Flat over nested — guard clauses, not pyramids; extract deep logic into helpers.
- Explicit over implicit — side effects and I/O visible at the call site; don't guess on
  ambiguous input, raise.
- Never a mutable (or non-constant) default argument — `None` + in-body init.
- Comprehensions: one `for`-clause and at most one filter; otherwise write a loop.
- Properties only for cheap, side-effect-free attribute access; otherwise a named method.
- Avoid `@staticmethod` (use a module function); `@classmethod` for named constructors.
- Lambdas stay one-line; name anything longer (lambdas can't be typed or tested).
- One function = one logical action — split anything that decomposes into separate steps.
- DRY hard — a function body that repeats another by ≥ 50% becomes one shared helper.
- Big or repeated type annotations → a `type` alias or a generic, not inlined on the function.

## Prime Directives (priority order)

- (1) Simpler — fewest parts, least nesting, no cleverness; redesign the hard-to-explain.
- (2) Faster — right algorithm + data structure; no repeated work in hot paths; cache pure fns.
- (3) Fewer machine resources — reuse pools/clients, stream not buffer, async I/O, batch.
- (4) Smaller code — stdlib over deps, DRY, inline single-use vars, delete dead code.
- (5) Less memory — `__slots__`, generators over lists, `tuple`/`frozenset`, bounded caches.
- (6) Safer — no `eval`/`shell=True`, parameterised SQL, `secrets`, validate input, narrow except.
- (7) Precise typing — annotate everything, no `Any`/`Optional`, concrete types, strict mypy.
- (8) Tighter docs — one-line public docstring, comments say WHY not what.
- When two conflict, prefer the earlier — never trade away correctness or safety.
