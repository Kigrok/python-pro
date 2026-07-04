# Dependencies — Standard Library First

Default to Python's standard library. Pull in a third-party package ONLY when stdlib
can't reasonably do the job. Pairs with the `check_stdlib` tool.

## Prefer stdlib over these

- `requests` → `urllib.request` / `http.client` (sync). Async at scale → `httpx` / `aiohttp`.
- `pytz` → `zoneinfo` (3.9+).
- `toml` (reading) → `tomllib` (3.11+).
- `simplejson` / `ujson` → `json`.
- `python-dateutil` (simple parse/format) → `datetime`.
- `six`, `pathlib2` → drop them (Python 3 / `pathlib`).
- `mock` → `unittest.mock`.
- `attrs` (simple records) → `dataclasses`.
- `click` / `typer` (small CLIs) → `argparse`.
- caching of pure functions → `functools.lru_cache`; thread/process pools → `concurrent.futures`.
- hashing / unique ids / tokens → `hashlib` / `uuid` / `secrets`.
- running commands → `subprocess` (never `shell=True`).

## When you DO add one — secure, low-level, fast, async

Priority order for picking a dependency:

- **Secure** — audited, actively maintained, small attack surface, no unsafe deserialization.
- **Async-native** — a real async API, not a sync library wrapped in threads.
- **Low-level / fast** — C/Rust-backed, minimal overhead.
- **Lean** — few transitive dependencies.

## Preferred picks (and what to avoid)

- Postgres → `asyncpg` (async, low-level). NOT `psycopg2` (sync).
- MySQL → `asyncmy` / `aiomysql`. NOT `pymysql` / `MySQLdb` (sync).
- MongoDB → `motor`. NOT `pymongo` (sync).
- HTTP client → `aiohttp` / `httpx`. NOT `requests` (sync).
- Web framework → `fastapi` + `uvicorn`/`uvloop`. NOT `flask` (sync).
- JSON in hot paths → `orjson` / `msgspec` (Rust/C, fast, safe). NOT `pickle` (insecure).
- Validation → `pydantic` v2 / `msgspec`. NOT `marshmallow` (slower).
- Crypto → `cryptography` (OpenSSL) / `PyNaCl` (libsodium). Never hand-rolled.

## How to decide

- If the task is one stdlib import away, do NOT add a package.
- If you add a dependency, prefer a House Stack / async-native library and state in one line why stdlib won't do.
- Pin the version in `requirements.txt`; don't add transitive-heavy packages for a one-liner.

## Packaging (pyproject.toml, PEP 621)

- Declare metadata in `pyproject.toml`: `[build-system]` (`requires` + `build-backend`)
  and `[project]` (name, version, dependencies).
- Runtime deps live in `[project].dependencies` — not only in `requirements.txt`.
- `requires-python = ">= 3.11"` — a minimum, never an upper bound.
- Feature / dev / test / doc deps go in `[project.optional-dependencies]` extras.
- Libraries constrain with `~=` / `>=`; pin exact `==` only in an application lock file.
- Apps (deployed services): commit a lock file pinning all transitive deps.
- One isolated venv per project; never install into system / user Python.
- `license = "MIT"` (SPDX string), not the deprecated table form.

This is the default for distributable packages and deployed apps. A tool/plugin may
deliberately stay on `pip` + `requirements.txt` (no `pyproject.toml`) — state that
choice explicitly in its README so the omission reads as intentional, not missing.
