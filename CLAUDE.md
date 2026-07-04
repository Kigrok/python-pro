# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **Claude Code plugin** named `python-pro` (v0.6.0) that enforces a production Python
3.11+ standard. It is both the plugin *and* a normal Python package — the same `cli/`
package powers every surface. The plugin ships:

- a **skill** (`skills/python-pro/SKILL.md`, the authoritative rule set),
- an **MCP server** (`mcp_server/server.py`, ~48 tools — lint/fix/validate/analyze,
  dependency graph, scaffolding/codegen, runtime testing, profiling, security, prompts),
- an **LSP server** (`lsp_server/server.py`, live diagnostics via pygls, wired through
  `.lsp.json`),
- **four hooks** (`hooks/hooks.json`): PreToolUse, PostToolUse, UserPromptSubmit, SessionStart,
- **six subagents** (`agents/*.md`): `api-builder`, `async-auditor`, `python-reviewer`,
  `refactor-modernizer`, `test-author`, `type-hardener`,
- a **slash command** (`commands/py-lint.md`).

It also targets non-Claude tools from the same source of truth: `.cursorrules` /
`.windsurfrules` (Cursor/Windsurf), `.github/copilot-instructions.md` (Copilot), `AGENTS.md`
(universal). All of these mirror `skills/python-pro/SKILL.md` — change that file first,
then propagate.

## Commands

Everything needs the repo root on `PYTHONPATH` because the packages import each other with
absolute names (`from cli.fixer import ...`).

```bash
# setup (pip + venv only — pyproject/poetry/uv are intentionally not used)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# tests
python3 tests/test_smoke.py              # standalone, no pytest needed — core smoke check
pytest                                   # test_smoke, test_hooks, test_benchmarks, test_scanners
pytest tests/test_hooks.py -k some_name  # single test

# CLI
PYTHONPATH=. python3 -m cli lint  <file.py> [--json] [--linters ruff,mypy]
PYTHONPATH=. python3 -m cli fix   <file.py>          # deterministic pipeline, residue only
PYTHONPATH=. python3 -m cli check <file.py>          # syntax only
PYTHONPATH=. python3 -m cli.validator        <dir>   # python-pro AST rule report
PYTHONPATH=. python3 -m cli.annotation_fixer <dir>   # missing annotations (report only)
PYTHONPATH=. python3 -m cli.type_analyzer    <file_or_dir>  # extract classes/functions/types

# MCP server (stdio) / LSP server — how the plugin launches them
bin/run-mcp.sh   # prefers .venv, sets PYTHONPATH, execs `python3 -m mcp_server.server`
bin/run-lsp.sh   # same, execs `python3 -m lsp_server.server`

# simulate a hook
echo '{"tool_name":"Write","tool_input":{"file_path":"cli/models.py"}}' | python3 hooks/post_edit.py

# validate the plugin manifest
claude plugin validate .
```

There is no single linter entrypoint for the repo itself; run `ruff check .` / `mypy .`
(configs: `ruff.toml`, `mypy.ini` — `mypy.ini` runs strict: `disallow_untyped_defs`,
`disallow_incomplete_defs`, `warn_return_any`, `strict_equality`).

## Architecture

**Lint pipeline (`cli/`)** — the data flow is `linters.py` → `parser.py` → `models.py`:
- `linters.py` runs the 8 linters as parallel `asyncio` subprocesses (`LINTER_COMMANDS`),
  with a 30s per-linter timeout; a missing binary degrades to a failed `LinterResult`, never
  a crash.
- `parser.py` (`LinterParser` + `PARSERS` dispatch) turns each linter's stdout into
  `LintError`s via per-linter regexes.
- `models.py` holds the `@dataclass(slots=True)` results: `LintError` → `LinterResult` →
  `FileReport`.
- `fixer.py` shells out to `ruff --fix`, `black`, `isort`.

**Rule validator (`cli/validator.py`)** — pure-AST checks independent of the linters:
shebang, path comment, **public-only** one-line docstrings (warning), `__slots__`,
annotations, exact-name imports, `if/elif`→`match/case`, banned `Any`/`Optional` in
annotations, `== None`/`== True` comparisons, mutable default args, bare `except`,
wildcard imports, over-long functions, duplicate function bodies, broad `except Exception`,
`assert` outside tests, and `raise` without `from`. This encodes the same rules as
`skills/python-pro/SKILL.md`; change both together. The same validator backs the LSP
server's live diagnostics (`lsp_server/server.py` writes source to a temp file and maps
`ValidationIssue`s to LSP `Diagnostic`s).

**Codemods (`cli/codemods.py`)** — 10 idempotent AST-driven fixes ruff/black don't do
(`docs/codemods.md` has full before/after examples): shebang, path comment,
`from __future__ import annotations`, `__slots__` from `self.x`, `-> None` on void
single-line signatures, bare-`except` → `except Exception`, `contextlib.suppress`
rewrite, mutable-default and `if/elif`→`match/case` conversions, type-annotation
modernization. `Codemods.run()` runs the full set twice — before and after the ruff pass —
so ruff-introduced imports (e.g. SIM105's `import contextlib`) also get normalized.

**Deterministic pipeline (`cli/pipeline.py`)** — one call: semantic-cache check (skip
unchanged clean files) → codemods → `ruff --fix --unsafe-fixes` → `black` → codemods →
lint + validator + `cli/security.py` AST scan + `cli/metrics.py` complexity gate (CC > 10)
+ `cli/deps.py` stdlib-first check + annotation report. Returns only the residue
(`PipelineResult.summary()`); clean runs are cached via `cli/cache.py` (normalized-AST
blake2b hash). The hook, `fix_file`, and the CLI `fix` command all go through it.

**CodeGraph (`cli/codegraph.py`)** — whole-repo dependency graph (imports, exports,
classes, functions, transitive dependents, `affected_by`), persisted at
`~/.cache/python-pro/graph.json`. Backs the `deps_of`/`dependents_of`/`graph_of`/
`exports_of`/`affected_by`/`graph_summary`/`rebuild_graph` MCP tools and is preloaded by
`hooks/session_start.py` and `hooks/pre_edit.py`.

**Smart Context (`cli/smart_context.py`)** — runs lint, validate, security, complexity,
annotations, deps, graph, and skill-detection in parallel and returns one compact line
plus suggested actions, e.g.:
```
[3 issues] cli/type_analyzer.py | cc: analyze(12), _get_type(12) | affects 4 files | → Refactor 3 complex functions
```
This is what `hooks/post_edit.py` and the `smart_context` MCP tool return — the design
goal is zero wasted context on a clean file.

**Type tooling** — `type_analyzer.py` extracts signatures/types; `annotation_fixer.py`
(`AnnotationReporter`) **reports** missing annotations and never writes files (literal-only
inference, no guessing from calls/names).

**Scaffolding & codegen** — `cli/scaffolder.py` (`scaffold` MCP tool, used by the
`api-builder` subagent) and `cli/codegen.py` (`generate_code` MCP tool) produce
standard-conformant boilerplate (FastAPI routers, dataclass models, CLI skeletons).

**Runtime & performance tooling** — `cli/runtime.py` (`test_function`,
`check_types_runtime`), `cli/profiler.py` (`profiling_enable/disable/snapshot`),
`cli/performance.py` + `cli/optimizations.py` (`auto_refactor`, `optimization_stats`,
`refactor_suggestions`, `dead_code`), `cli/exec_cache.py` (execution caching,
`stale_files`, `clear_optimization_caches`). These back the MCP tools of the same name;
none of them run in the hook path — they're opt-in, called explicitly via MCP or CLI.

**MCP server (`mcp_server/server.py`)** — thin async wrappers over `cli/` and
`skills/detector.py`. `list_tools()` + a `match`-based `call_tool()` expose the full tool
set (grep `name="` in `mcp_server/server.py` for the current, authoritative list — it
spans lint/fix/validate/analyze, the CodeGraph tools, Smart Context, scaffolding/codegen,
runtime/profiling, security/complexity, and prompt-building helpers like
`compact_prompt`/`refactor_prompt`). `ReportFormatter` renders `FileReport` to text/dict.

**Hooks (`hooks/`, wired in `hooks/hooks.json`)**:
- `pre_edit.py` (PreToolUse, matcher `Write|Edit|MultiEdit`) — file context (exists/new,
  line count) and graph info *before* the AI writes.
- `post_edit.py` (PostToolUse, same matcher) — runs the deterministic pipeline, reports via
  `hookSpecificOutput.additionalContext` (exit 0, non-blocking), records remaining errors to
  memory.
- `user_prompt.py` (UserPromptSubmit) — injects the python-pro standard when the prompt text
  matches Python-related keywords (`_TRIGGERS` in that file).
- `session_start.py` (SessionStart) — preloads the CodeGraph, surfaces project stats and
  recurring `memory/patterns.json` issues.
- All four share `hooks/common.py::get_target()` to pull and filter the target `.py` path
  from the event payload, and bootstrap `sys.path` themselves since they run standalone
  (hence `# noqa: E402`).

`hooks/pre_commit.py` is a **standalone git hook** (has its own `main()`), not wired into
`hooks.json` — install it manually as `.git/hooks/pre-commit` if wanted. It is unrelated to
`cli/pre_commit.py` (`PreCommitFixer`), which backs the `pre_commit_fix` MCP tool.

**Subagents (`agents/*.md`)** — each is scoped to a narrow job and a narrow MCP tool
allowlist: `api-builder` (FastAPI endpoints), `async-auditor` (asyncio correctness),
`python-reviewer` (read-only review), `refactor-modernizer` (legacy → standard, behavior
preserved), `test-author` (pytest), `type-hardener` (kill `Any`/`Optional`, fill gaps).

**Skills (`skills/`)** — `python-pro/SKILL.md` is the auto-discovered plugin skill (the
authoritative rule set). The loose `skills/*.md` files (`async`, `http`, `database`,
`patterns`, `style`, `typing`, `logging`, `security`, …) are **rule data**, not skills:
`detector.py` (`SkillDetector`/`CodeAnalyzer`) string-matches code patterns and
concatenates the matching sheets via `get_rules()`. Adding a pattern category means adding
both a `PATTERNS` entry and a matching `skills/<name>.md`.

**Memory (`memory/__init__.py`)** — `PatternStorage` persists recurring linter errors to
`memory/patterns.json` (gitignored, created on first write); the hook records, the
`get_patterns` MCP tool surfaces them.

## Conventions specific to this repo

- **Absolute imports + `PYTHONPATH=.`** everywhere; standalone scripts (`hooks/*.py`,
  `lsp_server/server.py`, `tests/*.py`) bootstrap `sys.path` to the repo root before
  importing `cli`/`skills`/`memory` (hence the `# noqa: E402`).
- The plugin's own code must obey `skills/python-pro/SKILL.md`: shebang + path comment,
  annotations on everything, `__slots__` on namespace classes, exact-name imports,
  `match/case`, public-only one-line docstrings, `ClassVar` constants, no `Any`/`Optional`.
  (`cli/pre_commit.py` currently violates the exact-name-import rule itself — a known gap,
  not a pattern to copy.)
- `${CLAUDE_PLUGIN_ROOT}` is the path variable inside `plugin.json` / `hooks.json` /
  `.mcp.json` / `.lsp.json`.
- Linter version pins in `requirements.txt` are real and installed; don't relax them casually.
- `DOCS.md` and `REPORT.md` are historical (Russian-language) design notes from the initial
  build; both explicitly defer to `README.md`/`CLAUDE.md`/`AGENTS.md` for current behavior —
  don't treat them as authoritative.
