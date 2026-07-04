---
description: Lint, validate, and fix a Python file or directory to the python-pro standard (8 linters + AST rule validator)
---

## Target

Argument (file or directory): `$ARGUMENTS`

## Linter + validator output

!`R="${CLAUDE_PLUGIN_ROOT}"; PY="$R/.venv/bin/python"; [ -x "$PY" ] || PY=python3; PYTHONPATH="$R" "$PY" -m cli lint "$ARGUMENTS" 2>&1 || true`

!`R="${CLAUDE_PLUGIN_ROOT}"; PY="$R/.venv/bin/python"; [ -x "$PY" ] || PY=python3; PYTHONPATH="$R" "$PY" -m cli.validator "$ARGUMENTS" 2>&1 || true`

## Instructions

Fix every error and warning reported above so the target conforms to the python-pro
standard (strict typing, `__slots__`, exact-name imports, `match/case`, public-only
one-line docstrings, `ClassVar` constants, no `Any`/`Optional`). Re-run the linters
after editing to confirm a clean result. If `$ARGUMENTS` is empty, ask which file or
directory to check.
