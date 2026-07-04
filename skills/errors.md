# Error-Handling Rules

Exception rules under the python-pro standard.

## Catching
- Catch specific exceptions; never bare `except:` and never `except Exception` without re-raising.
- Don't swallow errors silently — log or propagate.
- Keep `try` blocks small; wrap only the line that can fail.

## Raising
- Raise precise built-ins or a small custom hierarchy; always include a message.
- Preserve the cause with `raise NewError(...) from exc`.
- Don't use exceptions for normal control flow on the happy path.

## Cleanup
- Release resources via context managers (`with`) or `finally`, not manual try/except.

```python
# good
try:
    data = parse(raw)
except ValueError as exc:
    raise ConfigError(f"bad config: {raw!r}") from exc
```

## More Catching Rules
- `except Exception` is allowed ONLY to log + `raise` — never to swallow.
- Never catch `BaseException` / `SystemExit` / `KeyboardInterrupt` (except at the process boundary).
- `try/except/else` — success-only code goes in `else`, not the `try` body.
- No `break` / `continue` / `return` in `finally` (swallows exceptions & results; `SyntaxWarning` from 3.14).

## Raising
- Custom exceptions derive `Exception`, end in `Error`, carry structured attrs (not just a string).
- `add_note(...)` to annotate an exception instead of wrapping it in a new one.
- `ExceptionGroup` + `except*` for several independent failures (e.g. concurrent tasks).

## contextlib
- `@contextmanager` must wrap `yield` in `try/finally`; if it catches, it must re-raise.
- `suppress(SpecificError)` only — never `suppress(Exception)`.
- `ExitStack` / `AsyncExitStack` for a dynamic number of context managers.
- `nullcontext()` as a no-op placeholder for an optional context manager.
