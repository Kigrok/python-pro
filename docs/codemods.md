# Codemods — Automatic AST Transformations

## Overview

The plugin contains **10 codemods** — deterministic AST transformations that fix code without AI involvement. Each codemod is idempotent: re-running changes nothing.

---

## 1. Shebang

**What it does:** Inserts `#!/usr/bin/env python3` at the top of the file.

**Before:**
```python
x: int = 1
```

**After:**
```python
#!/usr/bin/env python3
x: int = 1
```

---

## 2. Path Comment

**What it does:** Inserts `# filename.py` after the shebang.

**Before:**
```python
#!/usr/bin/env python3
x: int = 1
```

**After:**
```python
#!/usr/bin/env python3
# m.py
x: int = 1
```

---

## 3. Future Annotations

**What it does:** Inserts `from __future__ import annotations` for PEP 604 types.

**Before:**
```python
#!/usr/bin/env python3
# m.py
def greet(name: str) -> str:
    return f"Hello, {name}"
```

**After:**
```python
#!/usr/bin/env python3
from __future__ import annotations

# m.py
def greet(name: str) -> str:
    return f"Hello, {name}"
```

---

## 4. Add Slots

**What it does:** Computes `__slots__` from `self.x` in the class and inserts it.

**Before:**
```python
class User:
    def __init__(self):
        self.name = ""
        self.age = 0
```

**After:**
```python
class User:
    __slots__: tuple[str, ...] = ('name', 'age')
    def __init__(self):
        self.name = ""
        self.age = 0
```

---

## 5. Add Return None

**What it does:** Adds `-> None` to `__init__` methods missing a return annotation.

**Before:**
```python
class Box:
    def __init__(self):
        self.x = 1
```

**After:**
```python
class Box:
    def __init__(self) -> None:
        self.x = 1
```

---

## 6. Replace Bare Except

**What it does:** Replaces `except:` with `except Exception:`.

**Before:**
```python
try:
    risky()
except:
    pass
```

**After:**
```python
try:
    risky()
except Exception:
    pass
```

---

## 7. Suppress Try/Except/Pass

**What it does:** Replaces `try/except/pass` with `contextlib.suppress()`.

**Before:**
```python
try:
    risky()
except ValueError:
    pass
```

**After:**
```python
from contextlib import suppress

with suppress(ValueError):
    risky()
```

---

## 8. Rewrite Contextlib Suppress

**What it does:** Rewrites `import contextlib` + `contextlib.suppress(...)` to direct import.

**Before:**
```python
import contextlib

with contextlib.suppress(ValueError):
    pass
```

**After:**
```python
from contextlib import suppress

with suppress(ValueError):
    pass
```

---

## 9. Modernize Type Annotations

**What it does:** Replaces legacy `typing` types with built-in equivalents.

| Before | After |
|--------|-------|
| `Optional[X]` | `X \| None` |
| `Union[X, Y]` | `X \| Y` |
| `List[X]` | `list[X]` |
| `Dict[X, Y]` | `dict[X, Y]` |
| `Tuple[X, ...]` | `tuple[X, ...]` |
| `Set[X]` | `set[X]` |
| `FrozenSet[X]` | `frozenset[X]` |
| `Type[X]` | `type[X]` |

**Before:**
```python
from typing import Optional, List, Dict

def process(data: Optional[str] = None) -> List[str]:
    items: Dict[str, int] = {}
    return []
```

**After:**
```python
def process(data: str | None = None) -> list[str]:
    items: dict[str, int] = {}
    return []
```

---

## 10. Convert If/Elif to Match/Case

**What it does:** Converts `if/elif` chains (3+ branches) comparing a single variable to `match/case`.

**Before:**
```python
def get_color(code: int) -> str:
    if code == 1:
        return "red"
    elif code == 2:
        return "green"
    elif code == 3:
        return "blue"
    else:
        return "unknown"
```

**After:**
```python
def get_color(code: int) -> str:
    match code:
        case 1:
            return "red"
        case 2:
            return "green"
        case 3:
            return "blue"
        case _:
            return "unknown"
```

---

## Usage

### Via CLI
```bash
# Auto-fix file (all codemods)
PYTHONPATH=. python3 -m cli fix path/to/file.py

# Validate only (no write)
PYTHONPATH=. python3 -m cli lint path/to/file.py
```

### Via MCP
```json
{
  "tool": "auto_refactor",
  "arguments": {
    "file_path": "path/to/file.py",
    "dry_run": true
  }
}
```

### Programmatically
```python
from pathlib import Path
from cli.codemods import Codemods

# Apply all codemods
changes = Codemods.apply(Path("file.py"))
print(changes)  # ['shebang', 'future_annotations', 'added __slots__ to User']
```

---

## Execution Order

Codemods run in a specific sequence:

1. `_add_shebang` — add shebang
2. `_add_path_comment` — add path comment
3. `add_future_annotations` — add `from __future__ import annotations`
4. `add_slots` — add `__slots__` to classes
5. `_add_return_none` — add `-> None` to `__init__`
6. `replace_bare_except` — replace `except:` with `except Exception:`
7. `suppress_try_except_pass` — replace `try/except/pass` with `suppress`
8. `_rewrite_contextlib_suppress` — rewrite `contextlib.suppress`
9. `modernize_type_annotations` — modernize type annotations
10. `convert_ifelif_to_matchcase` — convert `if/elif` to `match/case`