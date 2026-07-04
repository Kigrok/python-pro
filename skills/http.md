# Python HTTP & Networking

Low-level, fast, lightweight HTTP patterns. Prefer speed over convenience.

## Library Priority

1. `aiohttp` — async, low-level, fast
2. `httpx` — async, modern, good API
3. `curl_cffi` — bypasses TLS fingerprinting
4. `urllib3` — sync, stdlib fallback

AVOID: `requests` (heavy, sync), `httpx` sync mode.

## aiohttp — Preferred

```python
from aiohttp import ClientSession, ClientTimeout

async def fetch(url: str) -> dict:
    timeout = ClientTimeout(total=30)
    async with ClientSession(timeout=timeout) as session:
        async with session.get(url) as resp:
            return await resp.json()
```

### Connection Pooling — Reuse Sessions

```python
# bad — new session per request
async def fetch(url: str) -> dict:
    async with ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json()

# good — shared session
_session: ClientSession | None = None

async def get_session() -> ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = ClientSession()
    return _session

async def fetch(url: str) -> dict:
    session = await get_session()
    async with session.get(url) as resp:
        return await resp.json()
```

### Timeouts — Always Set

```python
from aiohttp import ClientTimeout

timeout = ClientTimeout(
    total=30,      # total request time
    connect=10,    # connection establishment
    sock_read=10,  # reading response
)
```

### Connection Limits

```python
from aiohttp import TCPConnector

connector = TCPConnector(
    limit=100,           # max connections
    limit_per_host=30,   # per-host limit
    ttl_dns_cache=300,   # DNS cache TTL
)
```

## httpx — Modern Alternative

```python
from httpx import AsyncClient, Limits

async def fetch(url: str) -> dict:
    async with AsyncClient(timeout=30) as client:
        resp = await client.get(url)
        return resp.json()
```

### Connection Pool

```python
limits = Limits(
    max_connections=100,
    max_keepalive_connections=20,
)
```

## curl_cffi — TLS Fingerprint Bypass

```python
from curl_cffi.requests import AsyncSession

async def fetch(url: str) -> dict:
    async with AsyncSession() as session:
        resp = await session.get(url, impersonate="chrome")
        return resp.json()
```

## Parallel Requests

```python
import asyncio
from aiohttp import ClientSession

async def fetch_all(urls: list[str]) -> list[dict]:
    async with ClientSession() as session:
        async def _fetch(url: str) -> dict:
            async with session.get(url) as resp:
                return await resp.json()

        tasks = [_fetch(url) for url in urls]
        return await asyncio.gather(*tasks)
```

## Binary Downloads — Stream to Disk

```python
from aiohttp import ClientSession

async def download(url: str, path: str) -> None:
    async with ClientSession() as session:
        async with session.get(url) as resp:
            with open(path, "wb") as f:
                async for chunk in resp.content.iter_any():
                    f.write(chunk)
```

## WebSocket

```python
from aiohttp import ClientSession

async def ws_connect(url: str) -> None:
    async with ClientSession() as session:
        async with session.ws_connect(url) as ws:
            async for msg in ws:
                if msg.type == 1:  # TEXT
                    process(msg.data)
```

## Error Handling

```python
from aiohttp import ClientError, ClientTimeout

try:
    async with session.get(url) as resp:
        resp.raise_for_status()
        return await resp.json()
except ClientError as e:
    logger.error("Request failed: %s", e)
    return {}
```

## Security

- Always set `verify=True` (default)
- Validate SSL certificates
- Use timeouts to prevent hangs
- Limit response sizes

## Client Rules (httpx / aiohttp)

- Use a `Client` / `AsyncClient` (or `ClientSession`) instance — never top-level
  `httpx.get(...)` per call. Reuse one shared client; never create one per request.
- Always a context manager (`with` / `async with`), or `close()` / `aclose()` in `finally`.
- Set an explicit `timeout` on every client — don't rely on library defaults; never
  `timeout=None` in production.
- `raise_for_status()` before reading the body.
- Catch transport vs status errors separately (`httpx.RequestError` vs `HTTPStatusError`).
- Connection retries via `HTTPTransport(retries=N)`; read / 5xx retries via `tenacity`
  (back-off + jitter).
- In async code use the async read/stream methods (`aread`, `aiter_bytes`) — sync ones
  block the loop.
