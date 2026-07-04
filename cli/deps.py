#!/usr/bin/env python3
# cli/deps.py — Flag third-party imports replaceable by stdlib/faster async libs.

from __future__ import annotations

from ast import Import, ImportFrom, parse, walk
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_STDLIB_INSTEAD: Final[dict[str, str]] = {
    "requests": "urllib.request / http.client (async at scale -> httpx)",
    "pytz": "zoneinfo (3.9+)",
    "toml": "tomllib (3.11+, reading)",
    "simplejson": "json",
    "ujson": "json",
    "dateutil": "datetime (for simple parsing/formatting)",
    "six": "drop it (Python 3 only)",
    "pathlib2": "pathlib",
    "mock": "unittest.mock",
    "attr": "dataclasses (for simple records)",
    "attrs": "dataclasses (for simple records)",
    "click": "argparse (for simple CLIs)",
    "typer": "argparse (for simple CLIs)",
    "sh": "subprocess",
    "plumbum": "subprocess",
    "decorator": "functools.wraps",
    "more_itertools": "itertools + custom (check if builtin suffices)",
}

# Third-party that works but has a more secure / lower-level / faster async alternative.
_PREFER_FASTER: Final[dict[str, str]] = {
    "psycopg2": "asyncpg (async, low-level, fast Postgres)",
    "pymysql": "asyncmy / aiomysql (async MySQL)",
    "MySQLdb": "asyncmy / aiomysql (async MySQL)",
    "mysqlclient": "asyncmy / aiomysql (async MySQL)",
    "pymongo": "motor (async MongoDB)",
    "flask": "fastapi + uvicorn/uvloop (async, typed)",
    "marshmallow": "pydantic v2 / msgspec (faster, typed)",
    "pickle": "msgspec / json (pickle is unsafe on untrusted data)",
    "aiohttp": "httpx (cleaner API, better typing, http2)",
    "tornado": "fastapi + uvicorn (modern async web)",
}


@dataclass(slots=True)
class DependencyFinding:
    """A third-party import with a stdlib or safer/faster async alternative."""

    line: int
    module: str
    suggestion: str
    rule: str


class StdlibFirstChecker:
    """Flags third-party imports replaceable by stdlib or a safer async library."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def _root(module: str) -> str:
        """Return the top-level package of a dotted module path."""
        return module.split(".", 1)[0]

    @classmethod
    def _classify(cls, root: str, line: int, out: list[DependencyFinding]) -> None:
        """Append a finding if the package has a known better alternative."""
        if root in _STDLIB_INSTEAD:
            out.append(
                DependencyFinding(line, root, _STDLIB_INSTEAD[root], "stdlib-first"),
            )
        elif root in _PREFER_FASTER:
            out.append(
                DependencyFinding(line, root, _PREFER_FASTER[root], "prefer-async"),
            )

    @classmethod
    def _check(cls, node: object, out: list[DependencyFinding]) -> None:
        """Append findings for an import node touching a replaceable package."""
        match node:
            case Import():
                alias: object
                for alias in node.names:
                    cls._classify(cls._root(alias.name), node.lineno, out)
            case ImportFrom() if node.module is not None:
                cls._classify(cls._root(node.module), node.lineno, out)
            case _:
                pass

    @classmethod
    def findings(cls, file_path: str, tree: object = None) -> list[DependencyFinding]:
        """Structured stdlib-first / prefer-async findings (empty if clean)."""
        if tree is None:
            path: Path = Path(file_path)
            try:
                tree = parse(path.read_text(), str(path))
            except (OSError, SyntaxError):
                return []
        out: list[DependencyFinding] = []
        node: object
        for node in walk(tree):
            cls._check(node, out)
        out.sort(key=lambda f: f.line)
        return out

    @classmethod
    def check(cls, file_path: str) -> str:
        """Report third-party imports replaceable by stdlib or a safer async library."""
        findings: list[DependencyFinding] = cls.findings(file_path)
        if not findings:
            return f"{file_path}: dependencies OK (stdlib-first, async-native)"
        lines: list[str] = [f"{file_path}: {len(findings)} dependency suggestion(s)"]
        finding: DependencyFinding
        for finding in findings:
            lines.append(
                f"  line {finding.line} [{finding.rule}] "
                f"{finding.module} -> {finding.suggestion}",
            )
        return "\n".join(lines)
