#!/usr/bin/env python3
# tests/test_scanners.py — Tests for security, complexity, deps, and codegraph modules.

from __future__ import annotations

import ast
from pathlib import Path
from sys import exit
from sys import path as _sys_path
from tempfile import TemporaryDirectory
from typing import Final

_sys_path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli.codegraph import CodeGraph
from cli.deps import StdlibFirstChecker
from cli.metrics import ComplexityAnalyzer
from cli.security import SecurityScanner


def _write(tmp: str, name: str, body: str) -> Path:
    """Write a temp source file and return its path."""
    path: Path = Path(tmp) / name
    path.write_text(body)
    return path


def test_security_finds_eval() -> None:
    """Security scanner flags eval() calls."""
    body = (
        "#!/usr/bin/env python3\n"
        "# m.py\n"
        "def dangerous(x: str) -> object:\n"
        "    return eval(x)\n"
    )
    with TemporaryDirectory() as tmp:
        path = _write(tmp, "m.py", body)
        tree = ast.parse(body)
        findings = SecurityScanner.findings(str(path), tree)
        assert any(f.rule == "dangerous-eval" for f in findings)


def test_security_finds_exec() -> None:
    """Security scanner flags exec() calls."""
    body = (
        "#!/usr/bin/env python3\n"
        "# m.py\n"
        "def run(code: str) -> None:\n"
        "    exec(code)\n"
    )
    with TemporaryDirectory() as tmp:
        path = _write(tmp, "m.py", body)
        tree = ast.parse(body)
        findings = SecurityScanner.findings(str(path), tree)
        assert any(f.rule == "dangerous-eval" for f in findings)


def test_security_finds_shell_true() -> None:
    """Security scanner flags subprocess with shell=True."""
    body = (
        "#!/usr/bin/env python3\n"
        "# m.py\n"
        "import subprocess\n"
        "def run(cmd: str) -> None:\n"
        "    subprocess.run(cmd, shell=True)\n"
    )
    with TemporaryDirectory() as tmp:
        path = _write(tmp, "m.py", body)
        tree = ast.parse(body)
        findings = SecurityScanner.findings(str(path), tree)
        assert any(f.rule == "shell-injection" for f in findings)


def test_security_finds_weak_hash() -> None:
    """Security scanner flags md5/sha1 usage."""
    body = (
        "#!/usr/bin/env python3\n"
        "# m.py\n"
        "import hashlib\n"
        "def hash_data(data: bytes) -> str:\n"
        "    return hashlib.md5(data).hexdigest()\n"
    )
    with TemporaryDirectory() as tmp:
        path = _write(tmp, "m.py", body)
        tree = ast.parse(body)
        findings = SecurityScanner.findings(str(path), tree)
        assert any(f.rule == "weak-hash" for f in findings)


def test_security_clean_file() -> None:
    """Security scanner finds no issues in clean file."""
    body = (
        "#!/usr/bin/env python3\n"
        "# m.py\n"
        "def safe(x: int) -> int:\n"
        "    return x * 2\n"
    )
    with TemporaryDirectory() as tmp:
        path = _write(tmp, "m.py", body)
        tree = ast.parse(body)
        findings = SecurityScanner.findings(str(path), tree)
        assert len(findings) == 0


def test_complexity_simple_function() -> None:
    """Complexity analyzer reports low CC for simple function."""
    body = (
        "#!/usr/bin/env python3\n"
        "# m.py\n"
        "def simple(x: int) -> int:\n"
        "    return x + 1\n"
    )
    with TemporaryDirectory() as tmp:
        path = _write(tmp, "m.py", body)
        tree = ast.parse(body)
        result = ComplexityAnalyzer.over_threshold(str(path), 10, tree)
        assert len(result) == 0


def test_complexity_high_cc() -> None:
    """Complexity analyzer flags function with CC > 10."""
    body = (
        "#!/usr/bin/env python3\n"
        "# m.py\n"
        "def complex_func(x: int) -> str:\n"
        "    if x > 0:\n"
        "        if x > 10:\n"
        "            if x > 20:\n"
        "                if x > 30:\n"
        "                    if x > 40:\n"
        "                        if x > 50:\n"
        "                            if x > 60:\n"
        "                                if x > 70:\n"
        "                                    if x > 80:\n"
        "                                        if x > 90:\n"
        "                                            if x > 100:\n"
        "                                                return 'a'\n"
        "    return 'b'\n"
    )
    with TemporaryDirectory() as tmp:
        path = _write(tmp, "m.py", body)
        tree = ast.parse(body)
        result = ComplexityAnalyzer.over_threshold(str(path), 10, tree)
        assert len(result) > 0
        assert result[0].score > 10


def test_deps_finds_requests() -> None:
    """Deps checker flags requests (replaceable by httpx/urllib)."""
    body = (
        "#!/usr/bin/env python3\n"
        "# m.py\n"
        "import requests\n"
        "def fetch(url: str) -> str:\n"
        "    return requests.get(url).text\n"
    )
    with TemporaryDirectory() as tmp:
        path = _write(tmp, "m.py", body)
        tree = ast.parse(body)
        findings = StdlibFirstChecker.findings(str(path), tree)
        assert any(d.module == "requests" for d in findings)


def test_deps_finds_flask() -> None:
    """Deps checker flags flask (replaceable by fastapi)."""
    body = (
        "#!/usr/bin/env python3\n"
        "# m.py\n"
        "import flask\n"
        "app = flask.Flask(__name__)\n"
    )
    with TemporaryDirectory() as tmp:
        path = _write(tmp, "m.py", body)
        tree = ast.parse(body)
        findings = StdlibFirstChecker.findings(str(path), tree)
        assert any(d.module == "flask" for d in findings)


def test_deps_clean_stdlib() -> None:
    """Deps checker finds no issues with stdlib-only imports."""
    body = (
        "#!/usr/bin/env python3\n"
        "# m.py\n"
        "import os\n"
        "import json\n"
        "from pathlib import Path\n"
    )
    with TemporaryDirectory() as tmp:
        path = _write(tmp, "m.py", body)
        tree = ast.parse(body)
        findings = StdlibFirstChecker.findings(str(path), tree)
        assert len(findings) == 0


def test_codegraph_roundtrip() -> None:
    """CodeGraph can build and query exports."""
    body = (
        "#!/usr/bin/env python3\n"
        "# m.py\n"
        "def public_func() -> int:\n"
        "    return 42\n"
        "class MyClass:\n"
        "    pass\n"
    )
    with TemporaryDirectory() as tmp:
        path = _write(tmp, "m.py", body)
        graph = CodeGraph(root=tmp)
        graph.build()
        exports = graph.exports_of(str(path))
        assert "public_func" in exports
        assert "MyClass" in exports


_TESTS: Final[tuple] = (
    test_security_finds_eval,
    test_security_finds_exec,
    test_security_finds_shell_true,
    test_security_finds_weak_hash,
    test_security_clean_file,
    test_complexity_simple_function,
    test_complexity_high_cc,
    test_deps_finds_requests,
    test_deps_finds_flask,
    test_deps_clean_stdlib,
    test_codegraph_roundtrip,
)


def run() -> int:
    """Run every test; return a process exit code."""
    failed: int = 0
    for test in _TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    print(f"\n{len(_TESTS) - failed}/{len(_TESTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    exit(run())
