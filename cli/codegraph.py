#!/usr/bin/env python3
# cli/codegraph.py — Lightweight dependency graph for Python files.

from __future__ import annotations

from ast import (
    AsyncFunctionDef,
    ClassDef,
    FunctionDef,
    Import,
    ImportFrom,
    Module,
    parse,
)
from dataclasses import dataclass, field
from hashlib import blake2b
from json import dumps, loads
from pathlib import Path

from cli.constants import IGNORED_DIRS as _IGNORED


@dataclass(slots=True)
class FileNode:
    """One Python file's graph metadata."""

    path: str
    imports: list[str] = field(default_factory=list)
    imported_by: list[str] = field(default_factory=list)
    public_names: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    hash: str = ""


class CodeGraph:
    """In-memory dependency graph for a Python project."""

    __slots__: tuple[str, ...] = ("_nodes", "_root")

    def __init__(self, root: str | Path = ".") -> None:
        self._root: Path = Path(root).resolve()
        self._nodes: dict[str, FileNode] = {}

    @property
    def root(self) -> Path:
        return self._root

    def build(self) -> None:
        """Scan all .py files and build the graph."""
        self._nodes.clear()
        py_files: list[Path] = [
            p
            for p in self._root.rglob("*.py")
            if not any(part in _IGNORED for part in p.parts)
        ]
        for path in py_files:
            self._parse_file(path)
        self._resolve_imports()

    def _parse_file(self, path: Path) -> None:
        """Extract imports, classes, functions from a single file."""
        try:
            content: str = path.read_text()
            tree: Module = parse(content)
        except (OSError, SyntaxError):
            return

        rel: str = str(path.relative_to(self._root))
        node: FileNode = FileNode(path=rel)
        node.hash = blake2b(content.encode(), digest_size=8).hexdigest()

        for stmt in tree.body:
            if isinstance(stmt, Import):
                for alias in stmt.names:
                    node.imports.append(alias.name)
            elif isinstance(stmt, ImportFrom):
                if stmt.module:
                    node.imports.append(stmt.module)
                for alias in stmt.names or []:
                    node.public_names.append(alias.name)
            elif hasattr(stmt, "name"):
                name: str = stmt.name
                if name.startswith("_"):
                    continue
                node.public_names.append(name)
                if hasattr(stmt, "body"):
                    if isinstance(stmt, ClassDef):
                        node.classes.append(name)
                    elif isinstance(stmt, (FunctionDef, AsyncFunctionDef)):
                        node.functions.append(name)

        self._nodes[rel] = node

    def _resolve_imports(self) -> None:
        """Build reverse dependency map (imported_by)."""
        for node in self._nodes.values():
            for imp in node.imports:
                target: str | None = self._resolve_module(imp)
                if target and target in self._nodes:
                    self._nodes[target].imported_by.append(node.path)

    def _resolve_module(self, module: str) -> str | None:
        """Try to resolve a module name to a relative file path."""
        parts: list[str] = module.split(".")
        candidates: list[Path] = [
            self._root / "/".join(parts) / "__init__.py",
            self._root / ("/".join(parts) + ".py"),
        ]
        for c in candidates:
            if c.exists():
                return str(c.relative_to(self._root))
        return None

    def deps_of(self, file_path: str) -> list[str]:
        """Files that file_path imports (outgoing dependencies)."""
        node: FileNode | None = self._get(file_path)
        return node.imports if node else []

    def dependents_of(self, file_path: str) -> list[str]:
        """Files that import file_path (incoming dependencies)."""
        node: FileNode | None = self._get(file_path)
        return node.imported_by if node else []

    def exports_of(self, file_path: str) -> list[str]:
        """Public names exported by file_path."""
        node: FileNode | None = self._get(file_path)
        return node.public_names if node else []

    def graph_of(self, file_path: str, depth: int = 1) -> dict[str, object]:
        """Dependency subgraph around a file (outgoing + incoming, up to depth)."""
        visited: set[str] = set()
        result: dict[str, object] = {"file": file_path, "deps": [], "dependents": []}

        def _walk_deps(path: str, d: int) -> None:
            if path in visited or d > depth:
                return
            visited.add(path)
            node: FileNode | None = self._get(path)
            if not node:
                return
            for dep in node.imports:
                result["deps"].append({"file": dep, "depth": d})
                _walk_deps(dep, d + 1)

        def _walk_dependents(path: str, d: int) -> None:
            if path in visited or d > depth:
                return
            visited.add(path)
            node: FileNode | None = self._get(path)
            if not node:
                return
            for dep in node.imported_by:
                result["dependents"].append({"file": dep, "depth": d})
                _walk_dependents(dep, d + 1)

        _walk_deps(file_path, 1)
        _walk_dependents(file_path, 1)
        return result

    def summary(self, file_path: str) -> str:
        """Ultra-compact one-line dependency summary."""
        node: FileNode | None = self._get(file_path)
        if not node:
            return f"{file_path}: not indexed"
        deps: int = len(node.imports)
        rels: int = len(node.imported_by)
        pub: int = len(node.public_names)
        cls: int = len(node.classes)
        fn: int = len(node.functions)
        return (
            f"{node.path}: {deps} deps, {rels} dependents, "
            f"{pub} exports ({cls} classes, {fn} funcs)"
        )

    def affected_by(self, file_path: str) -> list[str]:
        """All files transitively affected if file_path changes."""
        result: list[str] = []
        queue: list[str] = [file_path]
        visited: set[str] = set()
        while queue:
            current: str = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            node: FileNode | None = self._get(current)
            if not node:
                continue
            for dep in node.imported_by:
                if dep not in visited:
                    result.append(dep)
                    queue.append(dep)
        return result

    def _get(self, file_path: str) -> FileNode | None:
        """Get node by relative or absolute path."""
        if file_path in self._nodes:
            return self._nodes[file_path]
        try:
            rel: str = str(Path(file_path).resolve().relative_to(self._root))
            return self._nodes.get(rel)
        except ValueError:
            return None

    def to_dict(self) -> dict[str, dict[str, object]]:
        """Serialize graph to dict for JSON persistence."""
        return {
            path: {
                "imports": n.imports,
                "imported_by": n.imported_by,
                "public_names": n.public_names,
                "classes": n.classes,
                "functions": n.functions,
                "hash": n.hash,
            }
            for path, n in self._nodes.items()
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, dict[str, object]],
        root: str | Path = ".",
    ) -> CodeGraph:
        """Deserialize graph from dict."""
        graph: CodeGraph = cls(root)
        for path, d in data.items():
            graph._nodes[path] = FileNode(
                path=path,
                imports=list(d.get("imports", [])),
                imported_by=list(d.get("imported_by", [])),
                public_names=list(d.get("public_names", [])),
                classes=list(d.get("classes", [])),
                functions=list(d.get("functions", [])),
                hash=str(d.get("hash", "")),
            )
        return graph

    def save(self, cache_path: Path | None = None) -> None:
        """Persist graph to JSON."""
        if cache_path is None:
            cache_path = Path.home() / ".cache" / "python-pro" / "graph.json"
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(dumps(self.to_dict(), indent=2, ensure_ascii=False))
        except OSError:
            pass

    @classmethod
    def load(cls, cache_path: Path | None = None, root: str | Path = ".") -> CodeGraph:
        """Load graph from JSON cache, or build fresh if missing."""
        if cache_path is None:
            cache_path = Path.home() / ".cache" / "python-pro" / "graph.json"
        try:
            data: dict[str, dict[str, object]] = loads(cache_path.read_text())
            return cls.from_dict(data, root)
        except (OSError, ValueError):
            graph: CodeGraph = cls(root)
            graph.build()
            graph.save(cache_path)
            return graph

    def update_file(self, file_path: str) -> bool:
        """Update a single file in the graph. Returns True if changed."""
        try:
            path: Path = Path(file_path).resolve()
            rel: str = str(path.relative_to(self._root))
            content: str = path.read_text()
            new_hash: str = blake2b(content.encode(), digest_size=8).hexdigest()

            old_node: FileNode | None = self._nodes.get(rel)
            if old_node and old_node.hash == new_hash:
                return False  # unchanged

            # Remove old reverse dependencies.
            if old_node:
                for imp in old_node.imports:
                    target: str | None = self._resolve_module(imp)
                    if target and target in self._nodes:
                        target_node: FileNode = self._nodes[target]
                        if rel in target_node.imported_by:
                            target_node.imported_by.remove(rel)

            # Parse fresh.
            self._parse_file(path)

            # Resolve new reverse dependencies.
            new_node: FileNode | None = self._nodes.get(rel)
            if new_node:
                for imp in new_node.imports:
                    target = self._resolve_module(imp)
                    if target and target in self._nodes:
                        target_node = self._nodes[target]
                        if rel not in target_node.imported_by:
                            target_node.imported_by.append(rel)

            return True
        except (OSError, SyntaxError):
            return False

    def update_files(self, file_paths: list[str]) -> int:
        """Update multiple files. Returns count of changed files."""
        changed: int = 0
        for fp in file_paths:
            if self.update_file(fp):
                changed += 1
        return changed

    def rebuild_incremental(self) -> int:
        """Rebuild only files that changed since last save. Returns count."""
        cache_path: Path = Path.home() / ".cache" / "python-pro" / "graph.json"
        try:
            old_data: dict[str, dict[str, object]] = loads(cache_path.read_text())
        except (OSError, ValueError):
            self.build()
            return len(self._nodes)

        changed: int = 0
        for path in self._root.rglob("*.py"):
            if any(part in _IGNORED for part in path.parts):
                continue
            rel: str = str(path.relative_to(self._root))
            try:
                content: str = path.read_text()
                new_hash: str = blake2b(content.encode(), digest_size=8).hexdigest()
                old_hash: str = str(old_data.get(rel, {}).get("hash", ""))
                if new_hash != old_hash:
                    self.update_file(str(path))
                    changed += 1
            except (OSError, SyntaxError):
                continue
        return changed

    def stats(self) -> dict[str, int]:
        """Get graph statistics."""
        total: int = len(self._nodes)
        total_imports: int = sum(len(n.imports) for n in self._nodes.values())
        total_classes: int = sum(len(n.classes) for n in self._nodes.values())
        total_functions: int = sum(len(n.functions) for n in self._nodes.values())
        return {
            "files": total,
            "imports": total_imports,
            "classes": total_classes,
            "functions": total_functions,
        }
