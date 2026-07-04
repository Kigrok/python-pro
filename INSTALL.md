# python-pro — Install in Claude Code

## Automatic Installation (skills-directory)

Plugin already copied to `~/.claude/skills/python-pro/`.

**Activation:**
1. Restart Claude Code
2. Check: `claude plugin list` — should show `python-pro@skills-dir`
3. Enable (if disabled): `claude plugin enable python-pro`

## Git Hooks Installation

For automatic pre-commit validation:

```bash
# In your Python project root
cp <path-to-python-pro>/hooks/pre_commit.py .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

Or add to `.git/hooks/pre-commit`:

```bash
#!/bin/bash
PYTHONPATH=<path-to-python-pro> python3 <path-to-python-pro>/hooks/pre_commit.py
```

## Verify It Works

```bash
# In a Python project
claude chat "fix this file" path/to/file.py
# or trigger the hook on edit:
# plugin automatically runs pipeline (codemods → ruff → black → lint → validator → security → complexity → deps)
```

## What the Plugin Does

- **Deterministic pipeline** (no AI): codemods (8 AST fixes) → ruff --fix → black → codemods (2nd pass) → lint + validator (19 AST rules) + security + complexity + deps
- **Semantic cache** — skips unchanged clean files (0 tokens)
- **Edit hook** — gives AI only residue (errors-first, compact)
- **Scaffolder** — generates conformant skeletons (module/service/fastapi/sqlalchemy/pydantic/pytest)
- **MCP server** — 12 tools (fix/validate/scaffold/outline/test/security/complexity/deps/annotate)
- **LSP** — pushes violations directly to editor (optional)

## Deactivation

```bash
claude plugin disable python-pro
# or full removal:
rm -rf ~/.claude/skills/python-pro
```

## Dev Mode (symlink)

Instead of copying to `~/.claude/skills/`, you can symlink:
```bash
ln -s <path-to-python-pro> ~/.claude/skills/python-pro
```
Edits in repo immediately visible to plugin (restart Claude Code after changes).