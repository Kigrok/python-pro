#!/usr/bin/env python3
# cli/codemods.py — Auto-refactor: AST transformations that write back to files.

from __future__ import annotations

import ast
import difflib
import io
import re
import tokenize
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "CodeFormatter",
    "CodemodResult",
    "Codemods",
    "DeadCodeAnalyzer",
    "ImportSorter",
]


@dataclass(slots=True)
class CodemodResult:
    """Result of a codemod transformation."""

    file: str
    changes: list[str] = field(default_factory=list)
    applied: bool = False
    diff: str = ""

    @property
    def count(self) -> int:
        return len(self.changes)

    def to_compact(self) -> str:
        if not self.applied:
            return f"{self.file}: no changes"
        return f"{self.file}: {self.count} codemod(s) applied"

    def to_diff(self) -> str:
        return self.diff


class CodemodEngine:
    """Apply AST transformations and write back to files."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def _read_source(file_path: str) -> str:
        try:
            return Path(file_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    @staticmethod
    def _write_source(file_path: str, source: str) -> None:
        Path(file_path).write_text(source, encoding="utf-8")

    @staticmethod
    def _make_diff(old: str, new: str, file_path: str) -> str:
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        return "".join(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
            )
        )

    @staticmethod
    def apply_all(
        file_path: str,
        dry_run: bool = True,
    ) -> CodemodResult:
        """Apply all codemods to a file. Returns result with diff."""
        source = CodemodEngine._read_source(file_path)
        if not source:
            return CodemodResult(file=file_path)

        result = CodemodResult(file=file_path)
        modified = source

        # Apply codemods in order.
        for codemod in [
            Codemods.remove_unused_imports,
            Codemods.sort_imports,
            Codemods.add_future_annotations,
            Codemods.add_slots,
            Codemods.replace_bare_except,
            Codemods.replace_isinstance_chain,
            Codemods.suppress_try_except_pass,
            Codemods.fix_mutable_defaults,
            Codemods.modernize_syntax,
        ]:
            new_source, changes = codemod(modified)
            if changes:
                modified = new_source
                result.changes.extend(changes)

        if modified != source:
            result.applied = True
            result.diff = CodemodEngine._make_diff(source, modified, file_path)
            if not dry_run:
                CodemodEngine._write_source(file_path, modified)

        return result


class Codemods:
    """Collection of AST-based codemods."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def apply(file_path: Path | str, dry_run: bool = False) -> list[str]:
        """Apply all codemods to a file. Returns list of changes applied."""
        path = Path(file_path) if isinstance(file_path, str) else file_path
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        all_changes: list[str] = []
        modified = source

        for codemod in [
            Codemods._add_shebang,
            Codemods._add_path_comment,
            Codemods.add_future_annotations,
            Codemods.add_slots,
            Codemods._add_return_none,
            Codemods.replace_bare_except,
            Codemods.suppress_try_except_pass,
            Codemods._rewrite_contextlib_suppress,
            Codemods.modernize_type_annotations,
            Codemods.convert_ifelif_to_matchcase,
        ]:
            new_source, changes = codemod(modified, path.name)
            if changes:
                modified = new_source
                all_changes.extend(changes)

        if modified != source and not dry_run:
            path.write_text(modified, encoding="utf-8")

        return all_changes

    @staticmethod
    def _add_shebang(source: str, filename: str = "") -> tuple[str, list[str]]:
        """Add shebang if missing."""
        if source.startswith("#!/"):
            return source, []
        return "#!/usr/bin/env python3\n" + source, ["shebang"]

    @staticmethod
    def _add_path_comment(source: str, filename: str = "") -> tuple[str, list[str]]:
        """Add a `# <filename>` comment after the shebang if none exists."""
        if not filename:
            return source, []
        lines = source.splitlines(keepends=True)
        if not (lines and lines[0].startswith("#!")):
            return source, []
        # Skip if an early comment already names this file (any path form,
        # e.g. the convention `# pkg/<name> — description`).
        base: str = filename.rsplit("/", 1)[-1]
        for existing in lines[1:4]:
            text: str = existing.lstrip()
            if text.startswith("#") and base in text:
                return source, []
        lines.insert(1, f"# {filename}\n")
        return "".join(lines), [f"path_comment:{filename}"]

    @staticmethod
    def _add_return_none(source: str, filename: str = "") -> tuple[str, list[str]]:
        """Add -> None to __init__ methods missing return type."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return source, []

        lines = source.splitlines(keepends=True)
        changes: list[str] = []

        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "__init__"
                and node.returns is None
            ):
                # Add -> None to the def line.
                line = lines[node.lineno - 1]
                if "->" not in line:
                    new_line = line.rstrip().rstrip(":") + " -> None:\n"
                    lines[node.lineno - 1] = new_line
                    changes.append("added -> None to __init__")

        if changes:
            return "".join(lines), changes
        return source, []

    @staticmethod
    def _rewrite_contextlib_suppress(
        source: str, filename: str = ""
    ) -> tuple[str, list[str]]:
        """Rewrite `import contextlib` + `contextlib.suppress(...)` to direct import."""
        if "import contextlib" not in source:
            return source, []
        if "contextlib.suppress(" not in source:
            return source, []

        # Add `from contextlib import suppress` import.
        lines = source.splitlines(keepends=True)
        new_lines = []
        import_added = False

        for line in lines:
            stripped = line.strip()
            if stripped == "import contextlib" and not import_added:
                new_lines.append("from contextlib import suppress\n")
                import_added = True
            elif stripped == "import contextlib" and import_added:
                # Remove duplicate import.
                continue
            else:
                new_lines.append(line)

        # Rewrite usage.
        result = "".join(new_lines)
        result = result.replace("contextlib.suppress(", "suppress(")

        if import_added:
            return result, ["rewrote contextlib.suppress → suppress"]
        return source, []

    @staticmethod
    def remove_unused_imports(source: str) -> tuple[str, list[str]]:
        """Remove unused imports using autoflake."""
        try:
            import autoflake

            result = autoflake.fix_code(
                source,
                remove_all_unused_imports=True,
                remove_unused_variables=True,
            )
            changes = []
            if result != source:
                old_lines = set(source.splitlines())
                new_lines = set(result.splitlines())
                removed = old_lines - new_lines
                for line in removed:
                    stripped = line.strip()
                    if stripped.startswith(("import ", "from ")):
                        changes.append(f"removed: {stripped}")
            return result, changes
        except ImportError:
            return source, []

    @staticmethod
    def sort_imports(source: str) -> tuple[str, list[str]]:
        """Sort imports using isort."""
        try:
            import isort

            result = isort.code(source, profile="black")
            changes = []
            if result != source:
                changes.append("sorted imports")
            return result, changes
        except ImportError:
            return source, []

    @staticmethod
    def add_future_annotations(
        source: str, filename: str = ""
    ) -> tuple[str, list[str]]:
        """Add `from __future__ import annotations` if missing."""
        if "from __future__ import annotations" in source:
            return source, []

        lines = source.splitlines(keepends=True)
        insert_pos = 0

        # Find position after shebang and encoding declaration.
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(("#!", "# -*-")) or stripped == "":
                insert_pos = i + 1
            elif stripped.startswith(('"""', "'''")):
                # Skip docstring.
                if stripped.count('"""') == 1 or stripped.count("'''") == 1:
                    for j in range(i + 1, len(lines)):
                        if '"""' in lines[j] or "'''" in lines[j]:
                            insert_pos = j + 1
                            break
                else:
                    insert_pos = i + 1
                break
            elif stripped.startswith("from __future__"):
                return source, []  # Already has it.
            else:
                break

        new_line = "from __future__ import annotations\n\n"
        lines.insert(insert_pos, new_line)
        return "".join(lines), ["future_annotations"]

    @staticmethod
    def _is_dataclass_decorator(decorator: ast.expr) -> bool:
        """True if a decorator is `dataclass` or `dataclass(...)`."""
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name):
            return target.id == "dataclass"
        if isinstance(target, ast.Attribute):
            return target.attr == "dataclass"
        return False

    @staticmethod
    def _defines_slots(item: ast.stmt) -> bool:
        """True if a class-body statement assigns __slots__ (plain or annotated)."""
        if isinstance(item, ast.AnnAssign):
            return isinstance(item.target, ast.Name) and item.target.id == "__slots__"
        if isinstance(item, ast.Assign):
            return any(
                isinstance(t, ast.Name) and t.id == "__slots__" for t in item.targets
            )
        return False

    @staticmethod
    def _class_body_insert_index(node: ast.ClassDef) -> int:
        """0-based line index to insert a slots line at (after any docstring)."""
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            return first.end_lineno or first.lineno
        return first.lineno - 1

    @staticmethod
    def add_slots(source: str, filename: str = "") -> tuple[str, list[str]]:
        """Add __slots__ to non-dataclass classes that are missing it."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return source, []

        lines = source.splitlines(keepends=True)
        changes: list[str] = []
        insertions: list[tuple[int, str]] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            # Skip dataclasses: @dataclass(slots=True) generates __slots__ itself,
            # and a manual __slots__ there is a TypeError at class creation.
            if any(Codemods._is_dataclass_decorator(d) for d in node.decorator_list):
                continue

            # Skip if __slots__ is already present (plain or annotated form).
            if any(Codemods._defines_slots(item) for item in node.body):
                continue

            methods = [
                m
                for m in node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            if len(methods) < 2:
                continue

            # Collect instance attributes assigned as self.<name> = ... in __init__.
            attrs: list[str] = []
            seen: set[str] = set()
            for method in methods:
                if method.name != "__init__":
                    continue
                for stmt in ast.walk(method):
                    if (
                        isinstance(stmt, ast.Attribute)
                        and isinstance(stmt.ctx, ast.Store)
                        and isinstance(stmt.value, ast.Name)
                        and stmt.value.id == "self"
                        and stmt.attr not in seen
                    ):
                        seen.add(stmt.attr)
                        attrs.append(stmt.attr)

            if attrs:
                body: str = ", ".join(repr(a) for a in attrs[:20])
                slots_line = f"    __slots__: tuple[str, ...] = ({body},)\n"
            else:
                # Namespace / static-only class: no instance state.
                slots_line = "    __slots__: tuple[str, ...] = ()\n"

            insertions.append((Codemods._class_body_insert_index(node), slots_line))
            changes.append(f"added __slots__ to {node.name}")

        # Apply insertions bottom-up so earlier indices stay valid.
        for index, slots_line in sorted(insertions, reverse=True):
            lines.insert(index, slots_line)

        return "".join(lines), changes

    @staticmethod
    def replace_bare_except(source: str, filename: str = "") -> tuple[str, list[str]]:
        """Replace bare `except:` with `except Exception:`."""
        changes: list[str] = []
        result = source

        # Simple regex-like replacement.
        lines = result.splitlines(keepends=True)
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped == "except:" or stripped == "except :":
                indent = line[: len(line) - len(line.lstrip())]
                new_lines.append(f"{indent}except Exception:\n")
                changes.append("replaced bare except")
            else:
                new_lines.append(line)

        return "".join(new_lines), changes

    @staticmethod
    def replace_isinstance_chain(
        source: str, filename: str = ""
    ) -> tuple[str, list[str]]:
        """Replace isinstance chains with match/case (3+ types)."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return source, []

        lines = source.splitlines(keepends=True)
        changes: list[str] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue

            # Check for isinstance chain: if isinstance(x, A): ... elif isinstance(x, B): ...
            chain: list[ast.If] = []
            current: ast.If | None = node
            while current and isinstance(current, ast.If):
                # Check if test is isinstance(x, Type)
                if (
                    isinstance(current.test, ast.Call)
                    and isinstance(current.test.func, ast.Name)
                    and current.test.func.id == "isinstance"
                    and len(current.test.args) == 2
                ):
                    chain.append(current)
                    if len(current.orelse) == 1 and isinstance(
                        current.orelse[0], ast.If
                    ):
                        current = current.orelse[0]
                    else:
                        break
                else:
                    break

            if len(chain) < 3:
                continue

            # Extract the variable and types.
            var_node = chain[0].test.args[0]
            if isinstance(var_node, ast.Name):
                var_name = var_node.id
            else:
                continue

            # Find end of chain.
            last = chain[-1]
            end_line = last.end_lineno or last.lineno

            # Build match/case.
            indent = " " * (node.col_offset)
            body_indent = indent + "    "
            case_indent = body_indent + "    "

            parts: list[str] = [f"{indent}match {var_name}:\n"]
            for item in chain:
                type_node = item.test.args[1]
                if isinstance(type_node, ast.Name):
                    pattern = type_node.id
                elif isinstance(type_node, ast.Attribute):
                    pattern = ast.dump(type_node)
                else:
                    pattern = ast.dump(type_node)

                body_lines: list[str] = []
                for stmt in item.body:
                    start = stmt.lineno - 1
                    end = stmt.end_lineno or stmt.lineno
                    for i in range(start, end):
                        body_lines.append(f"{case_indent}{lines[i].lstrip()}")

                parts.append(f"{body_indent}case {pattern}:\n")
                parts.extend(body_line + "\n" for body_line in body_lines)

            # Handle else.
            if len(last.orelse) > 0 and not isinstance(last.orelse[0], ast.If):
                parts.append(f"{body_indent}case _:\n")
                for stmt in last.orelse:
                    start = stmt.lineno - 1
                    end = stmt.end_lineno or stmt.lineno
                    for i in range(start, end):
                        parts.append(f"{case_indent}{lines[i].lstrip()}\n")

            replacement = "".join(parts)
            lines[node.lineno - 1 : end_line] = [replacement]
            changes.append(
                f"converted isinstance chain to match/case (line {node.lineno})"
            )

        if changes:
            return "".join(lines), changes
        return source, []

    @staticmethod
    def suppress_try_except_pass(
        source: str, filename: str = ""
    ) -> tuple[str, list[str]]:
        """Replace try/except/pass with contextlib.suppress."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return source, []

        lines = source.splitlines(keepends=True)
        changes: list[str] = []

        # Find try/except/pass blocks and rewrite them.
        replacements: list[tuple[int, int, str]] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            for handler in node.handlers:
                if not (
                    handler.type is None
                    and len(handler.body) == 1
                    and isinstance(handler.body[0], ast.Pass)
                ):
                    continue
                # Get the try body.
                indent = " " * (node.col_offset)
                body_indent = indent + "    "

                # Get exception type from handler.
                exc_type = "Exception"
                if isinstance(handler.type, ast.Name):
                    exc_type = handler.type.id
                elif isinstance(handler.type, ast.Attribute):
                    exc_type = ast.dump(handler.type)

                # Build with suppress statement.
                try_body_lines: list[str] = []
                for stmt in node.body:
                    start = stmt.lineno - 1
                    end = stmt.end_lineno or stmt.lineno
                    for i in range(start, end):
                        try_body_lines.append(f"{body_indent}{lines[i].lstrip()}")

                suppress_stmt = f"{indent}with suppress({exc_type}):\n"
                suppress_body = "".join(f"{line}\n" for line in try_body_lines)

                end_line = handler.end_lineno or handler.lineno
                replacement = suppress_stmt + suppress_body
                replacements.append((node.lineno - 1, end_line, replacement))
                changes.append(f"replaced try/except/pass with suppress({exc_type})")

        # Apply replacements in reverse order.
        for start, end, replacement in reversed(replacements):
            lines[start:end] = [replacement]

        # Add contextlib.suppress import if needed.
        if changes and "from contextlib import suppress" not in "".join(lines):
            lines.insert(0, "from contextlib import suppress\n")
            changes.append("added: from contextlib import suppress")

        if changes:
            return "".join(lines), changes
        return source, []

    @staticmethod
    def fix_mutable_defaults(source: str, filename: str = "") -> tuple[str, list[str]]:
        """Fix mutable default arguments: def f(x=[]) → def f(x=None) + x = x or []."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return source, []

        lines = source.splitlines(keepends=True)
        changes: list[str] = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            # Find mutable defaults.
            for i, default in enumerate(node.args.defaults):
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    # Get the argument name.
                    arg_index = len(node.args.args) - len(node.args.defaults) + i
                    if arg_index < 0 or arg_index >= len(node.args.args):
                        continue
                    arg = node.args.args[arg_index]
                    arg_name = arg.arg

                    # Replace default with None.
                    node.args.defaults[i] = ast.Constant(value=None)

                    # Add initialization in function body.
                    if isinstance(default, ast.List):
                        init = f"    {arg_name} = {arg_name} if {arg_name} is not None else []\n"
                    elif isinstance(default, ast.Dict):
                        init = f"    {arg_name} = {arg_name} if {arg_name} is not None else {{}}\n"
                    elif isinstance(default, ast.Set):
                        init = f"    {arg_name} = {arg_name} if {arg_name} is not None else set()\n"
                    else:
                        continue

                    # Insert after docstring or at start.
                    insert_pos = node.body[0].lineno - 1 if node.body else 0
                    if (
                        node.body
                        and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                    ):
                        insert_pos = 1

                    lines.insert(insert_pos, init)
                    changes.append(f"fixed mutable default for {arg_name}")

        if changes:
            return "".join(lines), changes
        return source, []

    @staticmethod
    def modernize_syntax(source: str, filename: str = "") -> tuple[str, list[str]]:
        """Modernize syntax using pyupgrade."""
        try:
            import pyupgrade

            result = pyupgrade.fix_code(
                source,
                pyupgrade._main._fix_py311_plus,
            )
            changes = []
            if result != source:
                changes.append("modernized syntax via pyupgrade")
            return result, changes
        except (ImportError, AttributeError):
            return source, []

    @staticmethod
    def convert_ifelif_to_matchcase(
        source: str, filename: str = ""
    ) -> tuple[str, list[str]]:
        """Convert if/elif chains (3+) comparing same variable to match/case."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return source, []

        lines = source.splitlines(keepends=True)
        changes: list[str] = []
        replacements: list[tuple[int, int, str]] = []  # (start, end, replacement)

        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue

            # Collect the chain: if -> elif -> elif -> ...
            chain: list[ast.If] = []
            current: ast.If | None = node
            while current and isinstance(current, ast.If):
                chain.append(current)
                if len(current.orelse) == 1 and isinstance(current.orelse[0], ast.If):
                    current = current.orelse[0]
                else:
                    break

            if len(chain) < 3:
                continue

            # Check if all compare the same variable.
            var_name: str | None = None
            valid = True
            for item in chain:
                if not isinstance(item.test, ast.Compare):
                    valid = False
                    break
                if (
                    len(item.test.ops) == 1
                    and isinstance(item.test.ops[0], (ast.Eq, ast.Is))
                    and len(item.test.comparators) == 1
                ):
                    comparator = item.test.comparators[0]
                    left = item.test.left
                    if isinstance(left, ast.Name) and isinstance(
                        comparator, ast.Constant
                    ):
                        if var_name is None:
                            var_name = left.id
                        elif var_name != left.id:
                            valid = False
                            break
                    else:
                        valid = False
                        break
                else:
                    valid = False
                    break

            if not valid or var_name is None:
                continue

            # Find the end of the chain (last elif's body end).
            last = chain[-1]
            end_line = last.end_lineno or last.lineno

            # Check if there's an else block.
            has_else = len(last.orelse) > 0 and not (
                len(last.orelse) == 1 and isinstance(last.orelse[0], ast.If)
            )

            # Build match/case.
            indent = " " * (node.col_offset)
            body_indent = indent + "    "
            case_indent = body_indent + "    "

            parts: list[str] = [f"{indent}match {var_name}:\n"]
            for item in chain:
                value = item.test.comparators[0]
                if isinstance(value, ast.Constant):
                    pattern = repr(value.value)
                else:
                    pattern = ast.dump(value)

                # Get body lines.
                body_lines: list[str] = []
                for stmt in item.body:
                    start = stmt.lineno - 1
                    end = stmt.end_lineno or stmt.lineno
                    for i in range(start, end):
                        body_lines.append(f"{case_indent}{lines[i].lstrip()}")

                parts.append(f"{body_indent}case {pattern}:\n")
                parts.extend(body_line + "\n" for body_line in body_lines)

            # Handle else.
            if has_else:
                else_stmts = last.orelse
                # Filter out If nodes that are part of the chain.
                actual_else = [s for s in else_stmts if not isinstance(s, ast.If)]
                if actual_else:
                    parts.append(f"{body_indent}case _:\n")
                    for stmt in actual_else:
                        start = stmt.lineno - 1
                        end = stmt.end_lineno or stmt.lineno
                        for i in range(start, end):
                            parts.append(f"{case_indent}{lines[i].lstrip()}\n")

            replacement = "".join(parts)
            replacements.append((node.lineno - 1, end_line, replacement))
            changes.append(
                f"converted if/elif chain to match/case (line {node.lineno})"
            )

        # Apply replacements in reverse order.
        for start, end, replacement in reversed(replacements):
            lines[start:end] = [replacement]

        if changes:
            return "".join(lines), changes
        return source, []

    @staticmethod
    def _apply_to_code_only(
        source: str,
        transform: Callable[[str], str],
    ) -> str:
        """Run a text transform on code only, leaving strings and comments intact.

        The type-modernization regexes match bare names like ``List[...]``. Applied
        to raw source they would also rewrite matches inside docstrings, string
        literals, and comments (e.g. code-generation templates). This masks every
        STRING and COMMENT token with a bracket-free sentinel, runs ``transform`` on
        the masked text (so the regexes still see across ``Name[...]`` tokens), then
        restores the original spans verbatim.
        """
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        except (tokenize.TokenError, IndentationError, SyntaxError):
            # Unparseable source: never risk corrupting it — transform nothing.
            return source

        lines: list[str] = source.splitlines(keepends=True)

        def _row(r: int) -> str:
            return lines[r - 1] if 0 <= r - 1 < len(lines) else ""

        def _slice(start: tuple[int, int], end: tuple[int, int]) -> str:
            (sr, sc), (er, ec) = start, end
            if sr == er:
                return _row(sr)[sc:ec]
            piece: list[str] = [_row(sr)[sc:]]
            piece.extend(_row(r) for r in range(sr + 1, er))
            piece.append(_row(er)[:ec])
            return "".join(piece)

        protected: dict[str, str] = {}
        masked: list[str] = []
        last_end: tuple[int, int] = (1, 0)
        for tok in tokens:
            masked.append(_slice(last_end, tok.start))
            if tok.type in (tokenize.STRING, tokenize.COMMENT):
                key: str = f"\x00{len(protected)}\x00"
                protected[key] = tok.string
                masked.append(key)
            else:
                masked.append(tok.string)
            last_end = tok.end

        transformed: str = transform("".join(masked))
        for key, original in protected.items():
            transformed = transformed.replace(key, original)
        return transformed

    @staticmethod
    def modernize_type_annotations(
        source: str, filename: str = ""
    ) -> tuple[str, list[str]]:
        """Modernize type annotations: X | None, list[X], dict[X, Y], etc."""
        # Mapping of old-style to new-style annotations.
        TYPE_MAP: dict[str, str] = {
            "List": "list",
            "Dict": "dict",
            "Tuple": "tuple",
            "Set": "set",
            "FrozenSet": "frozenset",
            "Type": "type",
        }

        changes: list[str] = []
        result = source

        # Handle Optional[X] → X | None (code tokens only, never inside strings).
        optional_pattern = re.compile(r"Optional\[([^\[\]]+)\]")
        if optional_pattern.search(result):
            result = Codemods._apply_to_code_only(
                result, lambda s: optional_pattern.sub(r"\1 | None", s)
            )
            changes.append("modernized Optional[X] → X | None")

        # Handle Union[X, Y] → X | Y.
        union_pattern = re.compile(r"Union\[([^\[\]]+)\]")
        if union_pattern.search(result):
            result = Codemods._apply_to_code_only(
                result, lambda s: union_pattern.sub(r"\1", s)
            )
            changes.append("modernized Union[X, Y] → X | Y")

        # Handle old-style generic types.
        for old, new in TYPE_MAP.items():
            pattern = re.compile(rf"\b{old}\[([^\[\]]+(?:\[[^\[\]]*\])?)\]")
            if pattern.search(result):
                result = Codemods._apply_to_code_only(
                    result, lambda s, p=pattern, n=new: p.sub(rf"{n}[\1]", s)
                )
                changes.append(f"modernized {old}[X] → {new}[X]")

        # Remove unused typing imports if we modernized.
        if changes:
            # Check if we can remove typing imports.
            typing_imports = [
                "Optional",
                "Union",
                "List",
                "Dict",
                "Tuple",
                "Set",
                "FrozenSet",
                "Type",
            ]
            for imp in typing_imports:
                # Check if the type is still used.
                if re.search(rf"\b{imp}\[", result):
                    continue
                # Remove from typing import.
                import_pattern = re.compile(
                    rf"from typing import ([^\n]*\b{imp}\b[^\n]*)\n"
                )
                match = import_pattern.search(result)
                if match:
                    imports = match.group(1)
                    new_imports = [
                        i.strip() for i in imports.split(",") if i.strip() != imp
                    ]
                    if new_imports:
                        result = (
                            result[: match.start()]
                            + f"from typing import {', '.join(new_imports)}\n"
                            + result[match.end() :]
                        )
                    else:
                        result = result[: match.start()] + result[match.end() :]

        if changes:
            return result, changes
        return source, []


@dataclass(slots=True)
class DeadCodeResult:
    """Result of dead code analysis."""

    file: str
    unused_imports: list[str] = field(default_factory=list)
    unused_functions: list[str] = field(default_factory=list)
    unused_classes: list[str] = field(default_factory=list)
    unused_variables: list[str] = field(default_factory=list)
    unreachable_code: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            len(self.unused_imports)
            + len(self.unused_functions)
            + len(self.unused_classes)
            + len(self.unused_variables)
            + len(self.unreachable_code)
        )

    def to_compact(self) -> str:
        if self.total == 0:
            return f"{self.file}: no dead code"
        parts = [f"{self.file}: {self.total} dead code items"]
        if self.unused_imports:
            parts.append(f"  imports: {', '.join(self.unused_imports[:5])}")
        if self.unused_functions:
            parts.append(f"  functions: {', '.join(self.unused_functions[:5])}")
        if self.unused_classes:
            parts.append(f"  classes: {', '.join(self.unused_classes[:5])}")
        if self.unused_variables:
            parts.append(f"  variables: {', '.join(self.unused_variables[:5])}")
        if self.unreachable_code:
            parts.append(f"  unreachable: {len(self.unreachable_code)} lines")
        return "\n".join(parts)


class DeadCodeAnalyzer:
    """Find dead code using vulture + AST analysis."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def analyze(file_path: str) -> DeadCodeResult:
        """Analyze file for dead code."""
        result = DeadCodeResult(file=file_path)

        # Use vulture for dead code detection.
        try:
            from vulture import Vulture

            v = Vulture()
            v.scan_file(file_path)
            dead = v.get_unused_code()

            for item in dead:
                if item.typ == "import":
                    result.unused_imports.append(item.name)
                elif item.typ in ("function", "method"):
                    result.unused_functions.append(item.name)
                elif item.typ == "class":
                    result.unused_classes.append(item.name)
                elif item.typ == "variable":
                    result.unused_variables.append(item.name)
        except ImportError:
            pass

        # AST-based unreachable code detection.
        try:
            source = Path(file_path).read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for i, stmt in enumerate(node.body):
                        if i > 0 and isinstance(stmt, (ast.Return, ast.Raise)):
                            prev = node.body[i - 1]
                            if isinstance(prev, (ast.Return, ast.Raise)):
                                result.unreachable_code.append(
                                    f"L{stmt.lineno}: unreachable after return/raise"
                                )
        except (OSError, SyntaxError):
            pass

        return result


@dataclass(slots=True)
class ImportSortResult:
    """Result of import sorting."""

    file: str
    sorted_count: int = 0
    diff: str = ""

    def to_compact(self) -> str:
        if self.sorted_count == 0:
            return f"{self.file}: imports already sorted"
        return f"{self.file}: {self.sorted_count} import(s) sorted"


class ImportSorter:
    """Sort imports using isort."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def sort(file_path: str, dry_run: bool = True) -> ImportSortResult:
        """Sort imports in file."""
        try:
            source = Path(file_path).read_text(encoding="utf-8", errors="replace")
            import isort

            sorted_source = isort.code(source, profile="black")

            if sorted_source == source:
                return ImportSortResult(file=file_path)

            old_lines = source.splitlines()
            new_lines = sorted_source.splitlines()
            changed = sum(
                1 for a, b in zip(old_lines, new_lines, strict=False) if a != b
            )

            result = ImportSortResult(file=file_path, sorted_count=changed)
            if not dry_run:
                Path(file_path).write_text(sorted_source, encoding="utf-8")

            diff = "\n".join(
                difflib.unified_diff(
                    source.splitlines(keepends=True),
                    sorted_source.splitlines(keepends=True),
                    fromfile=f"a/{file_path}",
                    tofile=f"b/{file_path}",
                )
            )
            result.diff = diff

            return result
        except ImportError:
            return ImportSortResult(file=file_path)


@dataclass(slots=True)
class FormatResult:
    """Result of code formatting."""

    file: str
    formatted: bool = False
    diff: str = ""

    def to_compact(self) -> str:
        if not self.formatted:
            return f"{self.file}: already formatted"
        return f"{self.file}: formatted"


class CodeFormatter:
    """Format code using black."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def format(file_path: str, dry_run: bool = True) -> FormatResult:
        """Format file with black."""
        try:
            import subprocess

            args = ["black", "--check", "--quiet", file_path]
            if not dry_run:
                args = ["black", "--quiet", file_path]

            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=30,
            )

            formatted = proc.returncode == 0
            return FormatResult(file=file_path, formatted=not formatted)

        except (subprocess.SubprocessError, OSError):
            return FormatResult(file=file_path)
