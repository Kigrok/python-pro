# GitHub Copilot Instructions — python-pro

This repo enforces a production Python 3.11+ standard. Follow these rules when generating code.

## Quick Reference

### Import Style (Exact-Name Only)

```python
# WRONG
import json
import asyncio
import os
import httpx

# CORRECT
from json import loads, dumps
from asyncio import run, gather
from os import environ
from httpx import AsyncClient, Client
```

### Type Annotations (Mandatory on Everything)

```python
# WRONG
def foo(x):
    y = x + 1
    return y

# CORRECT
def foo(x: int) -> int:
    y: int = x + 1
    return y
```

### Banned Types

- NO `Any` — use `object` if unconstrained
- NO `Optional[str]` — use `str | None`
- NO `Union[X, Y]` — use `X | Y` (Python 3.10+)

### Class Rules

```python
# WRONG
class Foo:
    MAX_SIZE = 100

# CORRECT
class Foo:
    __slots__ = ("x",)
    MAX_SIZE: ClassVar[int] = 100
```

### File Header (Every .py File)

```python
#!/usr/bin/env python3
# filename.py — One-line description.

from __future__ import annotations
```

### Comparisons

- `is None` / `is not None` — never `== None`
- `if flag:` / `if not flag:` — never `== True` / `== False`

### match/case Over if/elif

```python
# PREFERRED for 3+ branches
match command:
    case "start":
        start()
    case "stop":
        stop()
    case "pause":
        pause()
```

### Security

- NEVER `eval()` / `exec()` on dynamic input
- NEVER `subprocess` with `shell=True`
- NEVER `pickle.loads` on untrusted data
- Use `secrets` (not `random`) for tokens
- Use `hashlib.sha256+` (never `md5`/`sha1`) for security

### Testing

- Use `pytest` + `pytest-asyncio`
- Test every public function against empty/None/wrong-type/boundary inputs

## Architecture

- `cli/` — core package (CLI, MCP server, hooks share this code)
- `skills/python-pro/SKILL.md` — authoritative rule set
- `ruff.toml`, `mypy.ini` — linter configs
- `requirements.txt` — pinned versions (don't relax them)

## Running Checks

```bash
PYTHONPATH=. python3 -m cli lint <file.py>
PYTHONPATH=. python3 -m cli fix <file.py>
ruff check .
mypy .
```
