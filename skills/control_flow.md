#!/usr/bin/env python3
# skills/control_flow.md — PEP 572/634/654: Control Flow Patterns.

# Python Control Flow — PEP 572, PEP 634, PEP 654

## PEP 572: Assignment Expressions (Python 3.8+)

### Walrus Operator :=

```python
# BAD — separate assignment and condition
data = fetch_data()
if data:
    process(data)

# GOOD — walrus operator
if data := fetch_data():
    process(data)
```

### In While Loops

```python
# BAD
line = input()
while line != "quit":
    process(line)
    line = input()

# GOOD
while (line := input()) != "quit":
    process(line)
```

### In List Comprehensions

```python
# BAD
results = []
for x in data:
    y = expensive_function(x)
    if y is not None:
        results.append(y)

# GOOD
results = [y for x in data if (y := expensive_function(x)) is not None]
```

### In If Conditions

```python
# BAD
match = re.search(pattern, text)
if match:
    process(match.group(1))

# GOOD
if match := re.search(pattern, text):
    process(match.group(1))
```

### When NOT to Use

```python
# BAD — obscure code
if (n := len(data)) > 10:
    print(f"Too many items: {n}")

# GOOD — clear code
n = len(data)
if n > 10:
    print(f"Too many items: {n}")
```

## PEP 634: Structural Pattern Matching (Python 3.10+)

### Basic Matching

```python
def handle_command(command: str) -> None:
    match command:
        case "start":
            start_process()
        case "stop":
            stop_process()
        case "restart":
            restart_process()
        case _:
            unknown_command()
```

### Matching with Conditions

```python
def handle_status(code: int) -> str:
    match code:
        case 200:
            return "OK"
        case 301 | 302:
            return "Redirect"
        case 404:
            return "Not Found"
        case 500:
            return "Server Error"
        case _ if 400 <= code < 500:
            return "Client Error"
        case _ if 500 <= code < 600:
            return "Server Error"
        case _:
            return "Unknown"
```

### Matching with Capture

```python
def process_event(event: dict) -> None:
    match event:
        case {"type": "click", "x": x, "y": y}:
            handle_click(x, y)
        case {"type": "key", "code": code}:
            handle_key(code)
        case {"type": "mouse", "action": action}:
            handle_mouse(action)
        case _:
            unknown_event(event)
```

### Matching with Class Patterns

```python
from dataclasses import dataclass

@dataclass
class Point:
    x: float
    y: float

def classify(point: Point) -> str:
    match point:
        case Point(x=0, y=0):
            return "origin"
        case Point(x=0, y=_):
            return "y-axis"
        case Point(x=_, y=0):
            return "x-axis"
        case Point(x=x, y=y) if x == y:
            return "diagonal"
        case _:
            return "other"
```

### Matching with OR Patterns

```python
def handle_error(error: Exception) -> None:
    match error:
        case ValueError() | TypeError() as e:
            logger.error(f"Type error: {e}")
        case KeyError() as e:
            logger.error(f"Missing key: {e}")
        case _:
            logger.error(f"Unknown error: {error}")
```

### Matching with Guards

```python
def process_value(value: int) -> str:
    match value:
        case n if n < 0:
            return "negative"
        case 0:
            return "zero"
        case n if n > 0 and n < 100:
            return "small positive"
        case n if n >= 100:
            return "large positive"
```

## PEP 654: Exception Groups (Python 3.11+)

### Basic Exception Groups

```python
try:
    raise ExceptionGroup("multiple errors", [
        ValueError("bad value"),
        TypeError("bad type"),
    ])
except* ValueError as eg:
    print(f"Value errors: {eg.exceptions}")
except* TypeError as eg:
    print(f"Type errors: {eg.exceptions}")
```

### Creating Exception Groups

```python
errors: list[Exception] = []
for item in items:
    try:
        process(item)
    except ValueError as e:
        errors.append(e)

if errors:
    raise ExceptionGroup("processing failed", errors)
```

### Exception Group with Custom Exceptions

```python
class ValidationError(Exception):
    pass

class NotFoundError(Exception):
    pass

try:
    raise ExceptionGroup("validation failed", [
        ValidationError("name required"),
        ValidationError("email invalid"),
        NotFoundError("user not found"),
    ])
except* ValidationError as eg:
    for exc in eg.exceptions:
        print(f"Validation: {exc}")
except* NotFoundError as eg:
    for exc in eg.exceptions:
        print(f"Not found: {exc}")
```

### PEP 678: Enriching Exceptions with Notes

```python
try:
    process_data(data)
except ValueError as e:
    e.add_note(f"Processing file: {filename}")
    e.add_note(f"Data size: {len(data)} bytes")
    raise
```
## match/case — Idiom Rules

- Replace `isinstance()` dispatch chains with class patterns: `case Click(x=x, y=y):`.
- Switch to match/case once a value-dispatch `if/elif` reaches 3+ branches.
- A bare name in a `case` is a CAPTURE, not a comparison — constants must be dotted
  (`case Color.RED:`, never `case RED:`).
- Sequence patterns (`case [a, b]:`, `case [a, *rest]:`) replace `len()` + indexing;
  they do not match `str` or iterators — only `Sequence`.
- OR-pattern alternatives must bind the same names; capture with `as`:
  `case ("n" | "s") as d:`.
- Guards (`if ...`) only for non-structural constraints (ranges, membership).
- Plain classes need `__match_args__` for positional patterns (dataclasses get it free).
- Wildcard `case _:` is always last.

## Flow

- EAFP over LBYL — `try: d[k] except KeyError:` beats `if k in d` (no TOCTOU race).
- Guard clauses over nesting: return/raise early, keep the happy path flat.
