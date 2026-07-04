#!/usr/bin/env python3
# skills/data_structures.md — PEP 343/557/709: Data Structures.

# Python Data Structures — PEP 343, PEP 557, PEP 709

## PEP 343: Context Managers

### Basic Context Manager

```python
class FileOpener:
    def __init__(self, path: str) -> None:
        self.path = path
        self.file = None

    def __enter__(self) -> FileOpener:
        self.file = open(self.path, "r")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.file:
            self.file.close()
```

### Context Manager with @contextmanager

```python
from contextlib import contextmanager
from collections.abc import Iterator

@contextmanager
def timer(label: str) -> Iterator[None]:
    start: float = monotonic()
    yield
    elapsed: float = monotonic() - start
    print(f"{label}: {elapsed:.3f}s")
```

### Async Context Manager

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

@asynccontextmanager
async def get_session() -> AsyncIterator[ClientSession]:
    session: ClientSession = ClientSession()
    try:
        yield session
    finally:
        await session.close()
```

### Database Session

```python
@asynccontextmanager
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

## PEP 557: Data Classes

### Basic Data Class

```python
from dataclasses import dataclass, field

@dataclass
class Point:
    x: float
    y: float

# Auto-generates __init__, __repr__, __eq__
p1: Point = Point(1.0, 2.0)
p2: Point = Point(1.0, 2.0)
print(p1 == p2)  # True
```

### With Default Values

```python
@dataclass
class Config:
    host: str = "localhost"
    port: int = 8080
    debug: bool = False
```

### Mutable Defaults with field()

```python
@dataclass
class User:
    name: str
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
```

### Slots and Frozen

```python
@dataclass(slots=True)
class ImmutablePoint:
    x: float
    y: float

@dataclass(slots=True, frozen=True)
class FrozenPoint:
    x: float
    y: float
```

### With __post_init__

```python
@dataclass
class User:
    name: str
    email: str

    def __post_init__(self) -> None:
        if "@" not in self.email:
            raise ValueError("Invalid email")
```

### Class Variables

```python
from typing import ClassVar

@dataclass
class Counter:
    count: ClassVar[int] = 0
    name: str

    def __post_init__(self) -> None:
        Counter.count += 1
```

### Convert to Dict/Tuple

```python
from dataclasses import asdict, astuple

@dataclass
class User:
    name: str
    age: int

user: User = User("Alice", 30)
print(asdict(user))  # {'name': 'Alice', 'age': 30}
print(astuple(user))  # ('Alice', 30)
```

## PEP 709: Inlined Comprehensions (Python 3.12+)

### List Comprehensions

```python
# GOOD — list comprehension
squares: list[int] = [x ** 2 for x in range(100)]

# GOOD — with filtering
evens: list[int] = [x for x in range(100) if x % 2 == 0]

# GOOD — nested
flat: list[int] = [x for row in matrix for x in row]
```

### Dict Comprehensions

```python
# GOOD — dict comprehension
squared: dict[str, int] = {k: v ** 2 for k, v in data.items()}

# GOOD — filtering
filtered: dict[str, int] = {k: v for k, v in data.items() if v > 1}
```

### Set Comprehensions

```python
# GOOD — set comprehension
unique: set[int] = {x for x in numbers}
```

### Generator Expressions

```python
# GOOD — generator expression (lazy evaluation)
sum_of_squares: int = sum(x ** 2 for x in range(1000000))
```
## Dataclass Rules

- Mutable default → `field(default_factory=list)`; never a bare `[]` / `{}`.
- `@dataclass(slots=True)` by default; add `frozen=True` for immutables.
- Use `frozen=True`, never `unsafe_hash=True`, to get a safe `__hash__`.
- No default-valued field before a non-default one (also across inheritance).
- `ClassVar[...]` for class constants — otherwise they become instance fields.
- `InitVar[T]` for construct-only params (excluded from fields/repr/asdict).
- Prefer `@dataclass(frozen=True, slots=True)` over `NamedTuple` for new records.
- Introspect via `dataclasses.fields(x)`, not `__slots__`.

## Enum Rules

- Plain `Enum` by default; `IntEnum` / `StrEnum` / `IntFlag` only for raw-value interop.
- `@unique` when duplicate values would be a bug.
- Iterate the class (`for m in MyEnum:`) — `__members__` includes aliases.
- `Flag` over `IntFlag` for new bitwise flags.
