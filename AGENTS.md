# AGENTS.md

## What this is

Enforces a production **Python 3.11+** standard. Works with any AI coding tool — CLI and MCP server are universal. The `cli/` package powers all surfaces.

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

No pyproject/poetry/uv — pip + venv only, by design.

## Commands

All CLI commands require `PYTHONPATH=.` (absolute imports):

```bash
PYTHONPATH=. python3 -m cli lint  <file.py> [--json] [--linters ruff,mypy]
PYTHONPATH=. python3 -m cli fix   <file.py>           # auto-fix pipeline + residue report
PYTHONPATH=. python3 -m cli check <file.py>            # syntax only
PYTHONPATH=. python3 -m cli.validator        <dir>     # AST rule report
PYTHONPATH=. python3 -m cli.annotation_fixer <dir>     # missing annotations (report only)
```

## Tests

```bash
python3 tests/test_smoke.py   # standalone, no deps
pytest                         # optional, same tests
```

## Lint the repo itself

```bash
ruff check .    # config: ruff.toml
mypy .          # config: mypy.ini
```

No single all-linters entrypoint for self-checking.

## Key architecture

- **Pipeline** (`cli/pipeline.py`): codemods → `ruff --fix --unsafe-fixes` → black → codemods → lint + validator + security scan + complexity gate (CC > 10). Returns only residue. Semantic AST-hash cache skips unchanged clean files.
- **Smart Context** (`cli/smart_context.py`): Runs ALL checks in parallel (lint, validate, security, complexity, annotations, deps, graph, skills). Returns compact output + suggested actions. Zero context waste.
- **Hooks**:
  - `hooks/pre_edit.py`: PreToolUse — file context, tests, graph info BEFORE AI writes.
  - `hooks/post_edit.py`: PostToolUse — ALL checks run, compact context + actions.
  - `hooks/session_start.py`: SessionStart — project stats, graph preload, rules reminder.
  - `hooks/user_prompt.py`: UserPromptSubmit — triggers on Python-related keywords.
- **Skills** (`skills/*.md`): Rule data files, not loadable skills. `detector.py` pattern-matches code and concatenates matching sheets. Adding a category requires both a `PATTERNS` entry in `detector.py` and a `skills/<name>.md` file.
- **Validator** (`cli/validator.py`): Pure-AST checks. Rule set matches `skills/python-pro/SKILL.md` — change both together.
- **Codemods** (`cli/codemods.py`): Run twice (before and after ruff pass) so ruff-introduced imports also get fixed.
- **CodeGraph** (`cli/codegraph.py`): Full dependency graph with imports, exports, classes, functions, transitive dependents, affected_by. Persisted at `~/.cache/python-pro/graph.json`.

## Conventions

- Every `.py` file needs shebang + path comment + `from __future__ import annotations`.
- No `Any`, no `Optional` — use strict types. `__slots__` on namespace classes.
- `match/case` over `if/elif`. Exact-name imports. `ClassVar` for constants.
- Linter version pins in `requirements.txt` are real — don't relax them.
- `${CLAUDE_PLUGIN_ROOT}` is the path variable in `plugin.json` / `hooks.json`.
- `memory/patterns.json` is gitignored, created on first write.

## Gotchas

- Hook runs ruff only; full lint (mypy, pyright, etc.) requires `lint_file` MCP tool or CLI.
- `annotation_fixer.py` **reports** only, never writes files.
- Missing linter binary → failed `LinterResult`, never a crash.
- Standalone scripts (`hooks/*.py`, `tests/*.py`) bootstrap `sys.path` themselves (`# noqa: E402`).

## Multi-AI integration

This repo provides config files for multiple AI tools:

| Tool | File | Description |
|------|------|-------------|
| Claude Code | `CLAUDE.md` | Full rules + MCP + hooks |
| Cursor / Windsurf | `.cursorrules` | Core rules for autocomplete |
| GitHub Copilot | `.github/copilot-instructions.md` | Rules for chat completions |
| Any AI | `AGENTS.md` | This file — universal reference |

All files reference the same authoritative source: `skills/python-pro/SKILL.md`. Change that file first, then propagate to others.

## Smart Context output

After every file edit, the hook returns compact context:

```
[OK] cli/pipeline.py | exports: annotations, gather | affects 3 files | skills: async, errors
[3 issues] cli/type_analyzer.py | cc: analyze(12), _get_type(12) | affects 4 files | → Refactor 3 complex functions
```

The AI gets: status, exports, affected files, applicable skills, and suggested actions — all in 1-2 lines.
