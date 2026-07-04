# Python Database Patterns

SQLAlchemy 2 async + asyncpg. Optimize queries, prevent injection, save memory.

## Library Choice

1. `SQLAlchemy 2 async` — ORM + query builder
2. `asyncpg` — fastest PostgreSQL driver
3. `alembic` — migrations

AVOID: `psycopg2` (sync), `databases` (abandoned).

## Connection Pool — Essential

```python
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost/db",
    pool_size=20,        # connections in pool
    max_overflow=40,     # extra connections
    pool_timeout=30,     # wait for connection
    pool_recycle=1800,   # recycle idle connections
    pool_pre_ping=True,  # validate connections
)
```

## Session Management

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

SessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

## Query Optimization

### Use select() Not query()

```python
# bad
users = await session.query(User).all()

# good
from sqlalchemy import select
result = await session.execute(select(User))
users = result.scalars().all()
```

### Select Only Needed Columns

```python
# bad — fetches entire row
result = await session.execute(select(User))

# good — specific columns
result = await session.execute(
    select(User.id, User.name, User.email)
)
```

### Use limit() Always

```python
# bad — fetches all
result = await session.execute(select(User))

# good — bounded
result = await session.execute(
    select(User).limit(100)
)
```

### Filter Early

```python
# bad — filters after fetch
result = await session.execute(select(User))
users = [u for u in result if u.active]

# good — filters in SQL
result = await session.execute(
    select(User).where(User.active == True)
)
```

## Eager Loading — Avoid N+1

```python
from sqlalchemy.orm import selectinload

# bad — N+1 queries
users = await session.execute(select(User))
for user in users:
    keys = await session.execute(
        select(Key).where(Key.user_id == user.id)
    )

# good — eager load
result = await session.execute(
    select(User).options(selectinload(User.keys))
)
```

## Bulk Operations

```python
# bad — one by one
for item in items:
    session.add(item)
await session.flush()

# good — bulk insert
session.add_all(items)
await session.flush()
```

## Memory-Efficient Streaming

```python
# bad — loads all into memory
result = await session.execute(select(User))
users = result.scalars().all()

# good — stream one by one
result = await session.execute(select(User))
for user in result.scalars():
    process(user)
```

## SQL Injection Prevention

```python
# bad — string interpolation
query = f"SELECT * FROM users WHERE name = '{name}'"

# good — parameterized
from sqlalchemy import text
result = await session.execute(
    text("SELECT * FROM users WHERE name = :name"),
    {"name": name},
)
```

### Use ORM Filters

```python
# good — ORM handles escaping
result = await session.execute(
    select(User).where(User.name == name)
)
```

## Transactions

```python
async def transfer(from_id: int, to_id: int, amount: int) -> None:
    async with SessionFactory() as session:
        async with session.begin():
            sender = await session.get(User, from_id)
            receiver = await session.get(User, to_id)
            sender.balance -= amount
            receiver.balance += amount
        # auto-commit on exit, auto-rollback on exception
```

## Column Types — Use Smallest Possible

```python
from sqlalchemy import SmallInteger, Integer, BigInteger

# bad
id: int = Column(Integer)

# good — for small ranges
status: int = Column(SmallInteger)  # 2 bytes vs 4

# good — for large IDs
id: int = Column(BigInteger)  # only when needed
```

## Column Metadata — Always Specify

Every column MUST have `name`, `comment`, and `nullable` specified.

```python
from sqlalchemy import String, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column

# bad — no metadata
class User(Base):
    name = Column(String)
    email = Column(String)

# good — explicit metadata
class User(Base):
    __tablename__ = "users"
    __table_args__ = {"comment": "Application users table"}

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True,
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="User display name",
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True,
        comment="User email address",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        comment="Account active status",
    )
```

## Indexes — Always Add

```python
from sqlalchemy import Index

class User(Base):
    __tablename__ = "users"

    id: int = Column(Integer, primary_key=True)
    email: str = Column(String(255), unique=True, index=True)
    status: str = Column(String(20), index=True)

    __table_args__ = (
        Index("ix_user_status_email", "status", "email"),
    )
```

## Common Mistakes

```python
# bad — no timeout on queries
result = await session.execute(select(User))

# bad — fetching all when need count
users = await session.execute(select(User))
count = len(users)

# good — count in SQL
from sqlalchemy import func
count = await session.scalar(select(func.count(User.id)))
```

## Session Rules (SQLAlchemy 2.0)

- 2.0-style `select()` + `session.execute()` / `session.scalars()` — never legacy
  `session.query()`.
- One Session per logical op via a context manager; never hold one open indefinitely.
- Frame writes with `session.begin()` (auto commit/rollback); `rollback()` after a flush
  failure before reuse.
- One `Engine` + one `sessionmaker` at app scope — never per request / function.
- Pass the Session INTO data-access functions; don't construct it inside them.
- Never share a `Session` across threads, or an `AsyncSession` across concurrent tasks
  (one per thread / per task); use `scoped_session` / `async_scoped_session` for a global handle.
- `session.get(Model, pk)` for primary-key lookups (hits the identity map).
- No `commit()` on read-only work.
