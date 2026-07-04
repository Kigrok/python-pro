# Report: python-pro — What Was Done, Why, How It Works

## Goal
The plugin writes/refactors Python **maximally professionally** (PEP, SOLID, patterns, + house rules) while **minimizing AI tokens**: everything that can be done deterministically by code is done by code; AI only gets what requires judgment.

---

## 1. Rule Base — Sources and Content

**Why:** The standard must rest on official sources, not taste.

**What was done:** Via research workflow, **262 rules** collected from official sources:
- PEP 8/257/484/544/585/604/695/636/654
- docs.python.org (typing, asyncio, dataclasses, pathlib)
- mypy/typing best-practices
- bandit security
- packaging.python.org
- pydantic v2, FastAPI, pytest, httpx, SQLAlchemy 2.0
- Black/Ruff official profiles
- Google Python Style Guide

On top — **9 "Prime Directives"** (simpler → faster → fewer resources → less code → less memory → safer → more precise types → more compact docs → **lower level, fewer dependencies**).

**Rule conflicts** resolved in favor of **official** sources:
- Multi-line docstring per PEP 257 (not Google style)
- Module-level functions/constants allowed
- `match/case` as recommendation for 3+ branches
- **`import x` forbidden** (house rule) — plugin code converted to `from x import ...`

---

## 2. "Code Instead of AI" — Core Mechanism

**Why:** Every token AI spends on mechanics (formatting, imports, type stubs) is waste. The pipeline squeezes mechanics into code.

**How it works — `DeterministicPipeline.run` (one call):**
```
semantic-cache check → codemods → ruff --fix --unsafe-fixes (15 families)
→ black → codemods (2nd pass) → lint + validator + security + complexity + deps
→ compact residue (only what AI needs)
```

**6 codemods** (`cli/codemods.py`, AST-driven, idempotent):
| codemod | what it does |
|---|---|
| shebang | inserts `#!/usr/bin/env python3` |
| path_comment | inserts `# path/to/file.py — description` |
| future_annotations | inserts `from __future__ import annotations` |
| **import_rewrite** | `import x` → `from x import ...` (when x only used as `x.attr`); also fixes imports ruff itself introduces |
| **slots** | computes `__slots__` from `self.x` in class and inserts |
| **return_none** | `-> None` on void single-line-signature functions (generators/value-return untouched) |

**Why 2nd codemod pass:** ruff (SIM105) itself introduces `import contextlib` — second pass rewrites it so the plugin doesn't create its own violation.

**What remains for AI:** Only semantic — docstring content, replacing `eval`, inferring non-obvious return types, manual refactor of large/duplicating functions.

---

## 3. Checks — Why Stricter

**Why:** The more defects code catches deterministically, the less work and risk for AI.

### Validator (`cli/validator.py`) — **19 AST rules**:
- shebang, path_comment, docstring, slots, annotation
- import-x (ban `import x`), match_case (3+), banned_type (Any/Optional)
- none/bool-comparison, mutable_default, bare_except, **broad_except**, **assert** (outside tests), **raise_from** (B904)
- wildcard_import, function_length (>60 stmt), duplicate_code

### Security (`cli/security.py`) — **wired into pipeline**:
AST scan: eval/exec/shell/pickle/secrets/weak-hash

### Complexity (`cli/metrics.py`) — **wired into pipeline**:
Cyclomatic complexity gate (CC > 10)

### Dependencies (`cli/deps.py`) — **new, wired into pipeline**:
Stdlib-first scan: flags third-party packages replaceable by stdlib or safer/faster/async-native alternatives:
- `requests` → `urllib.request` / `httpx`
- `flask` → `fastapi`
- `pytz` → `zoneinfo`
- `click` → `argparse`
- `psycopg2` → `asyncpg`
- `aiohttp` → `httpx`
- and 18 more

### Linters (ruff.toml extended):
15 families: E,F,I,UP,B,SIM,C4,RUF,PERF,PIE,FURB,RET,PTH,TID,BLE

### Types (mypy.ini + pyrightconfig.json):
strict mode: `disallow_incomplete_defs`, `warn_return_any`, `strict_equality`

---

## 4. Semantic Caching + Prompt Compression

**Why:** Don't re-validate unchanged; don't load extra text into AI.

### Semantic Cache (`cli/cache.py`):
- Normalized AST → blake2b hash
- Structurally-unchanged clean file = **short-circuit**: ruff/black/validator **don't run**, hook is silent (0 tokens)
- Toggle: `PYTHON_PRO_NO_CACHE=1`

### Prompt Compression:
- SKILL.md and sheets compressed: **~−2600 tokens** (removed PEP demo blocks, duplicates, foreign Django code)
- 5 "dead" sheets (`control_flow/data_structures/modern_python/style/typing`) now actually loaded via narrow low-FP patterns in `detector.py`
- **Compact residue** — `PipelineResult.summary()` gives AI only residue (errors-first, with cap); clean file = empty string

---

## 5. What AI Sees in Practice (E2E)

Dirty AI-generated file (old typing, `==None`, `=[]` default, no-slots, no-annot, `import x`, unused, bare-except):

**Before:**
- 10+ violations (unused imports, `Optional/List`, `==None`, mutable-default, bare-except, no-slots, no-annot, `import x`, no-shebang, no-path-comment, no-`-> None`)

**After deterministic pipeline (0 AI tokens):**
- unused imports removed
- `Optional/List` → `|`/`list`
- `==None` → `is None`
- mutable-default → `None` + init
- bare-except → `contextlib.suppress`
- shebang/path/future/slots/`-> None` inserted
- `import contextlib` rewritten to `from contextlib import suppress`

**AI receives:**
- 3 docstring contents (semantic)
- 1 real return type (inference)

Was ~10 violations → AI sees 4. The rest — free, done by code.

---

## 6. Verified Current State

| Check | Result |
|---|---|
| `ruff check .` | **0** |
| `tests/test_smoke.py` | **10/10** |
| self-validate (own AST rules) | **0 errors** |
| `py_compile` whole repo | **OK** |
| plugin.json validation | **✔ passed** |

**Caveat:** This shell only has `ruff` (no `mypy/pyright/black/isort`) — their logic verified via unit tests and `py_compile`; full set runs in env with pins from `requirements.txt`.

---

## 7. "Code Instead of AI" Inventory

- **10 codemods**: shebang, path_comment, future_annotations, **import_rewrite**, **slots**, **return_none**, **type_annotations**, **match/case**, **suppress_try_except**, **rewrite_contextlib**
- **19 AST checks** in validator (including broad_except, assert, raise_from added in this session)
- **security + complexity + deps** on every run
- **semantic cache** (AST-hash)
- **ruff** 15 rule families
- **mypy/pyright** strict mode

---

## 8. Installation in Claude Code

Plugin copied to `~/.claude/skills/python-pro/` (skills-directory).

**Activation:**
1. Restart Claude Code
2. Check: `claude plugin list` — should show `python-pro@skills-dir`
3. Enable (if disabled): `claude plugin enable python-pro`

**What the plugin does:**
- Edit hook → deterministic pipeline → AI gets only residue
- MCP server: 12 tools (fix/validate/scaffold/outline/test/security/complexity/deps/annotate)
- LSP (optional): pushes violations to editor
- Scaffolder: generates conformant skeletons (0 errors out of the box)

**Dev mode (symlink):**
```bash
ln -s <path-to-python-pro> ~/.claude/skills/python-pro
```
Edits in repo immediately visible to plugin (restart Claude Code after changes).

---

## 9. What Was Strengthened This Session

| Finding | Strengthening |
|---|---|
| ruff SIM105 introduced `import contextlib` (self-own) | codemod **import_rewrite** + 2nd codemod pass after ruff |
| `slots` went to AI | codemod **slots** (computed from `self.x`) |
| return annotations on void functions → AI | codemod **return_none** (only void + single-line signature) |
| scaffolder `UserService`→`UserServiceService` | fix (`removesuffix`) |
| security/complexity — dead MCP-only path | wired into pipeline (caught on every edit) |
| broad-except / assert / raise-from not caught | 3 new AST checks |
| mypy/ruff weak | strict mypy +3, ruff +9 families |
| SKILL/sheets bloated | −2600 tokens, orphan-sheets now loaded |
| re-linting clean files | Semantic Cache (AST-hash) |
| "low-level-ness" not in rules | **9th directive + deps checker in pipeline** |

---

## Summary

The plugin **minimizes AI work** (mechanics → code) and **maximizes quality** (262 rules, 9 directives, 19 AST checks, security, complexity, stdlib-first deps scan).

**AI tokens spent only on meaning**, everything else handled by deterministic pipeline.

Installed at `~/.claude/skills/python-pro/`, ready to use after restarting Claude Code.