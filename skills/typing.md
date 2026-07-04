#!/usr/bin/env python3
# skills/typing.md — PEP 484/526/544/585/604/612/655/673/681/695/698: Type System.

# Python Typing — rules (PEP 484-698 syntax is standard)

## Best Practices (strict mypy)

- Import abstract types from `collections.abc` (`Iterable`, `Sequence`, `Mapping`,
  `Iterator`, `Callable`) — NOT from `typing` (deprecated aliases).
- Params take abstract types (`Iterable[int]`); returns are concrete (`list[int]`).
- `object`, not `Any`, when a value is unconstrained but only stringified/stored.
- Annotate empty containers and `None`-init: `items: list[str] = []`.
- Generators return `Iterator[T]`; `__init__` returns `None`.
- `float` already accepts `int` — don't write `int | float`.
- Avoid union *return* types — redesign to one concrete type or raise.
- `Final[T]` for never-reassigned; `ClassVar[T]` for class-only attributes.
- No bare `# type: ignore` — always `# type: ignore[code]` with a reason.

## Protocols & generics

- `@runtime_checkable` only when you actually `isinstance()` it (checks attribute
  presence only, and is slow).
- `Protocol` with `__call__` for callables `Callable[...]` can't express
  (keyword-only / overloaded signatures).
- `ParamSpec` (`[**P]`) forwards exact params through decorators — not `Callable[..., Any]`.
- `TypeIs` over `TypeGuard` when the narrowed type is a subtype of the input.
- `TypedDict` + `NotRequired` / `ReadOnly`; `Unpack[TD]` to type `**kwargs`.

## Factor large annotations

- When a function's type structure grows big or repeats (nested unions, long
  `Callable[...]`, repeated `dict[str, list[tuple[...]]]`), do NOT inline it on one
  function. Extract it:
  - a named `type` alias (PEP 695): `type Handler = Callable[[Request], Awaitable[Response]]`;
  - a generic parameter when the shape is reused across types: `def first[T](xs: Sequence[T]) -> T`;
  - a `Protocol` / `TypedDict` when it is a structural contract.
- A signature should read as one idea — push the type detail into the alias/generic.

## PEP 695 syntax (3.12+)

- `def f[T](...)`, `class C[T]`, `type Alias[T] = ...` — no `Generic[T]` base, no
  `Protocol[T]` subscription (it is implied).
- Never mix a legacy `TypeVar` with bracket params in one definition.
- A type param used once is useless — use a concrete union.
- Type params are not in scope in defaults or decorators.
- A constrained param needs 2+ literal types: `[T: (str, bytes)]`.
- `Self` for methods returning self/cls — but not for a factory that always builds the base.
