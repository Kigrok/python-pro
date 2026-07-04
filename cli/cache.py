#!/usr/bin/env python3
# cli/cache.py — Semantic AST-hash cache: skip re-processing unchanged structure.

from __future__ import annotations

from ast import Module, dump, parse
from contextlib import suppress
from hashlib import blake2b
from json import dumps, loads
from os import environ
from pathlib import Path
from tempfile import gettempdir

_CACHE_DIR: Path = Path(gettempdir()) / "python-pro-cache"
_PERSISTENT_DIR: Path = Path.home() / ".cache" / "python-pro"


def _cache_dir() -> Path:
    """Use persistent dir if available, fall back to temp."""
    try:
        _PERSISTENT_DIR.mkdir(parents=True, exist_ok=True)
        return _PERSISTENT_DIR
    except OSError:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        return _CACHE_DIR


class SemanticCache:
    """Cache keyed by a file's normalized-AST hash; skip clean unchanged files."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def enabled() -> bool:
        """Whether caching is on (env PYTHON_PRO_NO_CACHE=1 disables it)."""
        return environ.get("PYTHON_PRO_NO_CACHE", "0") == "0"

    @staticmethod
    def ast_hash(file_path: str) -> str:
        """Structural hash, ignoring formatting, comments, and line numbers."""
        try:
            tree = parse(Path(file_path).read_text())
        except (OSError, SyntaxError):
            return ""
        body: str = dump(tree, annotate_fields=False)
        return blake2b(body.encode(), digest_size=16).hexdigest()

    @staticmethod
    def parse_tree(file_path: str) -> Module | None:
        """Parse file and return AST tree, or None on error."""
        try:
            return parse(Path(file_path).read_text())
        except (OSError, SyntaxError):
            return None

    @staticmethod
    def is_clean(file_path: str, ast_hash: str) -> bool:
        """True when this exact structure was previously recorded as residue-free."""
        if not ast_hash or not SemanticCache.enabled():
            return False
        entry: dict[str, object] = SemanticCache._load(file_path)
        return entry.get("hash") == ast_hash and entry.get("clean") is True

    @staticmethod
    def mark_clean(file_path: str, ast_hash: str) -> None:
        """Record that this structure produced zero residue."""
        if ast_hash and SemanticCache.enabled():
            SemanticCache._store(file_path, {"hash": ast_hash, "clean": True})

    @staticmethod
    def get_dirty_residue(file_path: str, ast_hash: str) -> list[str] | None:
        """Return cached residue lines for a dirty file, or None if no cache."""
        if not ast_hash or not SemanticCache.enabled():
            return None
        entry: dict[str, object] = SemanticCache._load(file_path)
        if entry.get("hash") == ast_hash and entry.get("clean") is False:
            residue: object = entry.get("residue", [])
            if isinstance(residue, list):
                return [str(r) for r in residue]
        return None

    @staticmethod
    def mark_dirty(file_path: str, ast_hash: str, residue: list[str]) -> None:
        """Cache dirty file residue to avoid re-running full pipeline."""
        if ast_hash and SemanticCache.enabled():
            SemanticCache._store(
                file_path,
                {"hash": ast_hash, "clean": False, "residue": residue[:20]},
            )

    @staticmethod
    def _key_path(file_path: str) -> Path:
        name: str = blake2b(file_path.encode(), digest_size=8).hexdigest()
        return _cache_dir() / f"{name}.json"

    @staticmethod
    def _load(file_path: str) -> dict[str, object]:
        try:
            return loads(SemanticCache._key_path(file_path).read_text())
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _store(file_path: str, data: dict[str, object]) -> None:
        with suppress(OSError):
            SemanticCache._key_path(file_path).write_text(dumps(data))
