#!/usr/bin/env python3
# cli/security.py — AST-based security checks against the python-pro standard.

from __future__ import annotations

from ast import Assign, Attribute, Call, Constant, Name, expr, parse, walk
from dataclasses import dataclass
from pathlib import Path
from typing import Final

__all__ = ["SecurityFinding", "SecurityScanner"]

_EVAL_CALLS: Final[frozenset[str]] = frozenset(
    {"eval", "exec", "compile", "__import__"},
)
_WEAK_HASHES: Final[frozenset[str]] = frozenset({"md5", "sha1"})
_SECRET_NAMES: Final[tuple[str, ...]] = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
)


@dataclass(slots=True)
class SecurityFinding:
    """A single security issue located at a source line."""

    line: int
    rule: str
    message: str


class SecurityScanner:
    """Scans a Python file's AST for common insecure patterns."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def _dotted(node: Call) -> tuple[str, str]:
        """Return (owner, name) for a call target; owner is '' if not attribute."""
        target: expr = node.func
        if isinstance(target, Attribute):
            owner: str = target.value.id if isinstance(target.value, Name) else ""
            return owner, target.attr
        if isinstance(target, Name):
            return "", target.id
        return "", ""

    @staticmethod
    def _has_shell_true(node: Call) -> bool:
        """True when a call passes shell=True."""
        keyword: object
        for keyword in node.keywords:
            value: object = keyword.value
            if (
                keyword.arg == "shell"
                and isinstance(value, Constant)
                and value.value is True
            ):
                return True
        return False

    @staticmethod
    def _is_secret_assign(node: Assign) -> bool:
        """True when a non-empty string literal is assigned to a secret-named target."""
        value: expr = node.value
        if not (isinstance(value, Constant) and isinstance(value.value, str)):
            return False
        if not value.value:
            return False
        target: expr
        for target in node.targets:
            name: str = target.id.lower() if isinstance(target, Name) else ""
            if any(part in name for part in _SECRET_NAMES):
                return True
        return False

    @classmethod
    def _check_call(cls, node: Call, out: list[SecurityFinding]) -> None:
        """Append findings for a single call node."""
        owner: str
        name: str
        owner, name = cls._dotted(node)
        match (owner, name):
            case (_, call) if call in _EVAL_CALLS:
                out.append(
                    SecurityFinding(
                        node.lineno,
                        "dangerous-eval",
                        f"avoid {call}()",
                    )
                )
            case ("os", "system"):
                out.append(
                    SecurityFinding(
                        node.lineno,
                        "shell-exec",
                        "os.system spawns a shell",
                    )
                )
            case ("yaml", "load"):
                out.append(
                    SecurityFinding(
                        node.lineno,
                        "unsafe-yaml",
                        "use yaml.safe_load",
                    )
                )
            case ("pickle", "load" | "loads"):
                out.append(
                    SecurityFinding(
                        node.lineno,
                        "unsafe-pickle",
                        "do not unpickle untrusted data",
                    )
                )
            case ("hashlib", hash_name) if hash_name in _WEAK_HASHES:
                out.append(
                    SecurityFinding(
                        node.lineno,
                        "weak-hash",
                        f"{hash_name} is weak; prefer sha256",
                    )
                )
            case _:
                pass
        if cls._has_shell_true(node):
            out.append(
                SecurityFinding(
                    node.lineno,
                    "shell-injection",
                    "subprocess shell=True",
                )
            )

    @classmethod
    def _inspect(cls, node: object, out: list[SecurityFinding]) -> None:
        """Append findings for one AST node."""
        match node:
            case Call():
                cls._check_call(node, out)
            case Assign() if cls._is_secret_assign(node):
                out.append(
                    SecurityFinding(
                        node.lineno,
                        "hardcoded-secret",
                        "secret as a literal",
                    )
                )
            case _:
                pass

    @classmethod
    def findings(cls, file_path: str, tree: object = None) -> list[SecurityFinding]:
        """Return structured security findings for a file (empty if clean)."""
        if tree is None:
            path: Path = Path(file_path)
            try:
                tree = parse(path.read_text(), str(path))
            except (OSError, SyntaxError):
                return []
        out: list[SecurityFinding] = []
        node: object
        for node in walk(tree):
            cls._inspect(node, out)
        out.sort(key=lambda f: f.line)
        return out

    @classmethod
    def scan(cls, file_path: str) -> str:
        """Return security findings for a file as text."""
        items: list[SecurityFinding] = cls.findings(file_path)
        if not items:
            return f"{file_path}: no security issues found"
        lines: list[str] = [f"{file_path}: {len(items)} security issue(s)"]
        finding: SecurityFinding
        for finding in items:
            lines.append(f"  line {finding.line} [{finding.rule}] {finding.message}")
        return "\n".join(lines)
