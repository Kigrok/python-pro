# Python Pro Plugin — Plan

> **Historical note.** This is the original project plan. Current architecture,
> file inventory, and commands are described in `README.md` and `CLAUDE.md`. Actual hooks:
> `post_edit.py`, `pre_commit.py`, `session_start.py`, `user_prompt.py`
> (no `pre_response.py` hook); master rules live in `skills/python-pro/SKILL.md`.

## Concept

A plugin for AI coding tools (Claude, Codex, Mimo) that:
- Replaces the existing python-pro skill
- Auto-detects active skills from code patterns
- Lints and fixes Python code through 8 linters
- Validates code against python-pro rules
- Saves tokens: AI writes code → plugin checks → AI fixes
- Learns from errors, recording patterns to memory

## Architecture

```
python-pro/
├── SKILL.md                 # Global rules + auto-detection
├── skills/
│   ├── __init__.py
│   ├── detector.py          # Skill auto-detection by patterns
│   ├── style.md             # PEP 8/257/701: Style and formatting
│   ├── typing.md            # PEP 484/526/544/585/604/612/655/673/681/695/698: Typing
│   ├── async.md             # PEP 492/525/530/3156: Async programming
│   ├── control_flow.md      # PEP 572/634/654: Control flow
│   ├── data_structures.md   # PEP 343/557/709: Data structures
│   ├── modern_python.md     # PEP 657/680/684/698/701/702: Modern Python
│   ├── patterns.md          # Patterns and algorithms
│   ├── database.md          # Databases and SQL
│   └── http.md              # HTTP and network requests
├── cli/
│   ├── __init__.py
│   ├── __main__.py          # CLI: python-pro lint/fix/check
│   ├── models.py            # LintError, LinterResult, FileReport
│   ├── linters.py           # Parallel run of 8 linters
│   ├── parser.py            # Parse output of each linter
│   ├── fixer.py             # Auto-fix (ruff --fix, black, isort)
│   ├── validator.py         # Validation against python-pro rules
│   └── type_analyzer.py     # Type analysis and docstring generation
├── mcp_server/
│   ├── __init__.py
│   └── server.py            # MCP tools: lint, fix, validate, detect_skills, analyze_types
├── hooks/
│   ├── __init__.py
│   ├── pre_response.py      # Pre-AI-response git change check
│   └── pre_commit.py        # Pre-commit validation
├── memory/
│   ├── __init__.py          # PatternStorage for error patterns
│   └── patterns.json        # Pattern store
├── requirements.txt
└── DOCS.md
```

## Components

### 1. CLI (`python-pro`)

Command: `python-pro lint <file_or_dir> [--json] [--fix]`

Behavior:
- Runs all 8 linters in parallel via `asyncio` + `subprocess`
- Parses output to compact format: `file:line:col:code:message`
- With `--fix`: auto-fixes (ruff --fix, black, isort)
- With `--json`: emits structured JSON for MCP/AI
- No flags: quiet mode, exit code (0 = OK, 1 = errors)

Linters:
| Linter  | Command              | Checks                |
|---------|----------------------|-----------------------|
| ruff    | `ruff check`         | Lint + import sorting |
| flake8  | `flake8`             | Style + errors        |
| black   | `black --check`      | Formatting            |
| isort   | `isort --check-only` | Import ordering       |
| mypy    | `mypy`               | Type checking         |
| pyright | `pyright`            | Type checking (stricter) |
| pylint  | `pylint`             | Code analysis         |
| vulture | `vulture`            | Dead code detection   |

Parallel run:
```python
async def run_all_linters(file_path: Path) -> list[LinterResult]:
    tasks = [
        run_linter("ruff", ["ruff", "check", str(file_path)]),
        run_linter("flake8", ["flake8", str(file_path)]),
        # ... all 8 linters
    ]
    results = await asyncio.gather(*tasks)
    return deduplicate(results)  # ruff may overlap with flake8
```

### 2. MCP Server

Tools:
- `lint_file(file_path: str) -> LinterResult[]` — run linters
- `fix_file(file_path: str) -> FixedResult` — auto-fix
- `check_syntax(file_path: str) -> bool` — fast syntax check
- `analyze_imports(file_path: str) -> ImportReport` — import analysis

Response format (no user output):
```json
{
  "status": "fixed",
  "file": "src/main.py",
  "errors_found": 12,
  "errors_fixed": 10,
  "remaining": [
    {"line": 45, "code": "E501", "message": "line too long"},
    {"line": 89, "code": "W503", "message": "line break before binary operator"}
  ]
}
```

### 3. Pre-response Hook

Script `hooks/pre_response.py`:
- Runs before every AI response (via agent hook system)
- Checks if any .py files changed in the session
- If yes — runs `python-pro lint --fix` in background
- Returns residual errors to AI (if any)
- AI fixes silently, without showing user

Integration:
- Claude: via CLAUDE.md instruction or MCP hook
- Codex: via plugin hooks in `.codex-plugin/plugin.json`
- Mimo: via skill hooks

### 4. SKILL.md

Skill structure:

```markdown
# Python Pro

## Code rules
- PEP 8/257/484 strictly
- SOLID principles
- __slots__ for classes
- async-first I/O
- Decimal for money
- Narrow exceptions
- Absolute imports

## Tools
Use `python-pro lint <file>` after writing/changing code.

## Auto-fix
On linter errors:
1. ruff/black/isort — auto-fix via `--fix`
2. mypy/pyright — fix types manually
3. pylint/vulture — delete dead code, refactor

## Learning
On recurring errors — write pattern to memory.
```

### 5. Memory / Learning

Record format:
```markdown
## [error-pattern · YYYY-MM-DD]
Pattern: <pattern description>
Linter: <linter name>
Code: <error code>
Fix: <how fixed>
Count: <occurrences>
```

Learning priority:
1. Frequent errors (>3 times) → add rule to SKILL.md
2. Rare errors → record in memory for reference
3. Project-specific rules → respect project configs

### 6. Configuration

Config resolution logic:
```
For each linter:
  1. Look for config in project root (ruff.toml, .flake8, mypy.ini, ...)
  2. If found — use it
  3. If not — use plugin's configs/
```

Supported configs:
- `ruff.toml` / `pyproject.toml [tool.ruff]`
- `.flake8` / `setup.cfg [flake8]`
- `mypy.ini` / `setup.cfg [mypy]`
- `pyrightconfig.json`
- `.pylintrc` / `pyproject.toml [tool.pylint]`
- `.isort.cfg` / `pyproject.toml [tool.isort]`
- `pyproject.toml [tool.black]`

## Implementation Phases

### Phase 1: CLI (basic) ✅
- [x] cli/__main__.py — entry point
- [x] cli/linters.py — run linters
- [x] cli/parser.py — parse output
- [x] cli/fixer.py — auto-fix
- [x] cli/models.py — data models
- [x] Testing on real files

### Phase 2: MCP Server ✅
- [x] mcp_server/server.py — tools
- [x] CLI integration
- [x] Import testing

### Phase 3: Hooks ✅
- [x] hooks/pre_response.py
- [x] Git change detection
- [x] Auto-fix + lint

### Phase 4: SKILL.md ✅
- [x] Rules (PEP, SOLID, async, memory, security)
- [x] CLI + MCP integration
- [x] Lint workflow

### Phase 5: Memory ✅
- [x] Pattern recording (patterns.json)
- [x] SKILL.md auto-update via format_patterns_for_skill()
- [x] Frequent errors (>3) → rules

## Requirements

- Python 3.11+
- All linters installed globally or in project venv
- MCP support in AI tool

## Token savings

Before plugin:
```
AI writes code (500 tokens)
AI analyzes linter errors (300 tokens)
AI fixes code (400 tokens)
Total: ~1200 tokens
```

After plugin:
```
AI writes code (500 tokens)
CLI runs linters (0 tokens)
AI gets compact error list (50 tokens)
AI fixes (200 tokens)
Total: ~750 tokens (−37%)
```

## Open questions

- [ ] Which MCP server to use? (mcp-python-sdk?)
- [ ] Need pyproject.toml integration for plugin configs?
- [ ] How to handle multi-module/package projects?
- [ ] Monorepo support needed?