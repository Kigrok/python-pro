# Logging Rules

Logging rules under the python-pro standard. Sources: Python `logging` HOWTO + cookbook.

## Loggers
- Module-level logger: `logger = getLogger(__name__)`. NEVER the root functions
  (`logging.info`, `logging.warning`) — they implicitly `basicConfig()` the root.
- Libraries attach ONLY a `NullHandler` to their top package logger; never
  `basicConfig()` and never add real handlers — handler/level config is the
  application's job.
- Never create a logger per request/connection (`getLogger(f"conn.{id}")`) — loggers
  are never garbage-collected, so this leaks. Inject context via `LoggerAdapter` or
  the `extra=` kwarg instead.

## Messages
- Pass args lazily — `logger.info("user %s in", name)`, NEVER pre-format with an
  f-string or `%`. Formatting is deferred until (and unless) the record is emitted.
- `logger.exception(...)` ONLY inside an `except` block — outside one it logs
  `NoneType: None` as the traceback.
- Guard expensive debug args with `logger.isEnabledFor(DEBUG)` — the *arguments* are
  still evaluated even when the level is off.
- No `print()` for diagnostics in importable code — it bypasses routing, filtering,
  and levels. `print` is for plain CLI stdout only.

## Levels & config
- Use the five standard levels (DEBUG/INFO/WARNING/ERROR/CRITICAL); libraries must not
  define custom numeric levels (they collide across libraries).
- `dictConfig` / `fileConfig`: set `disable_existing_loggers=False` (the default `True`
  silently kills loggers created at import time).
- Production: set `raiseExceptions = False` so a broken handler can't crash a worker.

## I/O & concurrency
- Slow handlers (SMTP, socket, network file) go behind a `QueueHandler` +
  `QueueListener` — a blocking handler stalls the calling thread / event loop.
- One file, many processes is unsupported by `FileHandler` — route through a single
  `QueueListener` or `SocketHandler` writer; concurrent writes corrupt the file.

```python
# good
from logging import getLogger, NullHandler

logger = getLogger(__name__)

def fetch(url: str) -> bytes:
    """Fetch the resource at url."""
    logger.debug("fetching %s", url)  # lazy args, named logger
    try:
        return _get(url)
    except TimeoutError:
        logger.exception("fetch failed for %s", url)  # inside except
        raise
```
