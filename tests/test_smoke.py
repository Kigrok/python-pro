#!/usr/bin/env python3
# tests/test_smoke.py — Standalone smoke tests for python-pro core (no pytest required).

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from sys import exit
from sys import path as _sys_path
from tempfile import TemporaryDirectory
from typing import Final

_sys_path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli.annotation_fixer import AnnotationReporter, MissingAnnotation
from cli.cache import SemanticCache
from cli.codemods import Codemods
from cli.models import FileReport, LinterResult, LintError, Severity
from cli.parser import parse_output
from cli.validator import (
    PythonProValidator,
    ValidationIssue,
    ValidationReport,
)
from skills.detector import SkillDetector


def _write(tmp: str, name: str, body: str) -> Path:
    """Write a temp source file and return its path."""
    path: Path = Path(tmp) / name
    path.write_text(body)
    return path


def test_parser_ruff() -> None:
    """ruff output parses into a LintError with code and position."""
    errors: list[LintError] = parse_output(
        "ruff",
        "x.py:3:5: F401 `os` imported but unused",
        "x.py",
    )
    assert len(errors) == 1
    assert errors[0].code == "F401"
    assert errors[0].line == 3 and errors[0].col == 5
    assert errors[0].linter == "ruff"


def test_models_total() -> None:
    """FileReport aggregates error counts across linters."""
    err: LintError = LintError(
        file="x.py",
        line=1,
        col=1,
        code="E001",
        message="m",
        linter="ruff",
        severity=Severity.ERROR,
    )
    report: FileReport = FileReport(
        file="x.py",
        results=[LinterResult(linter="ruff", success=False, errors=[err])],
    )
    assert report.total_errors == 1
    assert report.has_errors is True


def test_validator_flags_missing_shebang() -> None:
    """Validator reports a missing shebang on a bare module."""
    with TemporaryDirectory() as tmp:
        report: ValidationReport = PythonProValidator.validate(
            _write(tmp, "m.py", "x: int = 1\n"),
        )
        assert "shebang" in {i.rule for i in report.issues}


def test_validator_docstring_public_only() -> None:
    """Public functions trigger the docstring warning; private do not."""
    body: str = (
        "#!/usr/bin/env python3\n"
        "# m.py — t.\n"
        "def _helper() -> int:\n"
        "    return 1\n"
        "def public() -> int:\n"
        "    return 2\n"
    )
    with TemporaryDirectory() as tmp:
        report: ValidationReport = PythonProValidator.validate(
            _write(tmp, "m.py", body),
        )
        doc: list[ValidationIssue] = [i for i in report.issues if i.rule == "docstring"]
        names: str = " ".join(i.message for i in doc)
        assert "public()" in names
        assert "_helper" not in names
        assert all(i.severity == "warning" for i in doc)


def test_annotation_reporter_no_write() -> None:
    """Reporter flags a bare assignment and never mutates the file."""
    with TemporaryDirectory() as tmp:
        path: Path = _write(tmp, "m.py", "y = 5\n")
        before: str = path.read_text()
        issues: list[MissingAnnotation] = AnnotationReporter.check_file(path)
        assert any(i.name == "y" for i in issues)
        assert path.read_text() == before


def test_detector_async() -> None:
    """Detector activates the async skill on async code."""
    with TemporaryDirectory() as tmp:
        path: Path = _write(
            tmp,
            "m.py",
            "async def f() -> None:\n    await g()\n",
        )
        assert "async" in SkillDetector.detect(str(path))


def test_codemods_insert_header_and_future() -> None:
    """Codemods add shebang, path comment, and future import; idempotently."""
    with TemporaryDirectory() as tmp:
        path: Path = _write(tmp, "m.py", "x: int = 1\n")
        applied: list[str] = Codemods.apply(path)
        body: str = path.read_text()
        assert "shebang" in applied
        assert "future_annotations" in applied
        assert body.startswith("#!/usr/bin/env python3")
        assert "from __future__ import annotations" in body
        assert Codemods.apply(path) == []


def test_codemods_slots_return_none_import() -> None:
    """Codemods add __slots__, '-> None', and rewrite a bare import."""
    body: str = (
        "#!/usr/bin/env python3\n"
        "# m.py\n"
        "import contextlib\n"
        "class Box:\n"
        "    def __init__(self):\n"
        "        self.x = 1\n"
        "    def run(self):\n"
        "        with contextlib.suppress(ValueError):\n"
        "            pass\n"
    )
    with TemporaryDirectory() as tmp:
        path: Path = _write(tmp, "m.py", body)
        Codemods.apply(path)
        out: str = path.read_text()
        assert "__slots__" in out
        assert "def __init__(self) -> None:" in out
        assert "from contextlib import suppress" in out
        assert "suppress(ValueError)" in out


def test_semantic_cache_roundtrip() -> None:
    """A file marked clean reads back clean for the same AST hash."""
    with TemporaryDirectory() as tmp:
        path: Path = _write(tmp, "m.py", "x: int = 1\n")
        digest: str = SemanticCache.ast_hash(str(path))
        assert digest
        assert SemanticCache.is_clean(str(path), digest) is False
        SemanticCache.mark_clean(str(path), digest)
        assert SemanticCache.is_clean(str(path), digest) is True


def test_validator_broad_except_assert_raisefrom() -> None:
    """Validator flags broad except, assert outside tests, and raise without from."""
    body: str = (
        "#!/usr/bin/env python3\n"
        "# m.py\n"
        "def f(x: int) -> int:\n"
        "    assert x\n"
        "    try:\n"
        "        return x\n"
        "    except Exception:\n"
        "        raise ValueError('e')\n"
    )
    with TemporaryDirectory() as tmp:
        report: ValidationReport = PythonProValidator.validate(
            _write(tmp, "m.py", body),
        )
        rules: set[str] = {i.rule for i in report.issues}
        assert "broad_except" in rules
        assert "assert" in rules
        assert "raise_from" in rules


def test_codemod_matchcase_conversion() -> None:
    """Codemod converts if/elif chain (3+) to match/case."""
    body: str = (
        "#!/usr/bin/env python3\n"
        "# m.py\n"
        "def get_color(code: int) -> str:\n"
        "    if code == 1:\n"
        "        return 'red'\n"
        "    elif code == 2:\n"
        "        return 'green'\n"
        "    elif code == 3:\n"
        "        return 'blue'\n"
        "    else:\n"
        "        return 'unknown'\n"
    )
    result, changes = Codemods.convert_ifelif_to_matchcase(body, "m.py")
    assert len(changes) > 0
    assert "match code:" in result
    assert "case 1:" in result
    assert "case 2:" in result
    assert "case 3:" in result
    assert "case _:" in result


def test_codemod_matchcase_no_conversion() -> None:
    """Codemod doesn't convert if/elif with fewer than 3 branches."""
    body: str = (
        "#!/usr/bin/env python3\n"
        "# m.py\n"
        "def check(x: int) -> str:\n"
        "    if x == 1:\n"
        "        return 'one'\n"
        "    elif x == 2:\n"
        "        return 'two'\n"
        "    return 'other'\n"
    )
    with TemporaryDirectory():
        result, changes = Codemods.convert_ifelif_to_matchcase(body, "m.py")
        assert len(changes) == 0
        assert result == body


def test_codemod_type_annotations() -> None:
    """Codemod modernizes type annotations."""
    body: str = (
        "#!/usr/bin/env python3\n"
        "# m.py\n"
        "from typing import Optional, List, Dict\n"
        "def process(data: Optional[str] = None) -> List[str]:\n"
        "    items: Dict[str, int] = {}\n"
        "    return []\n"
    )
    result, changes = Codemods.modernize_type_annotations(body, "m.py")
    assert len(changes) > 0
    assert "str | None" in result
    assert "list[str]" in result
    assert "dict[str, int]" in result
    assert "from typing import" not in result


def test_codemod_type_annotations_idempotent() -> None:
    """Codemod type annotations is idempotent."""
    body: str = (
        "#!/usr/bin/env python3\n"
        "# m.py\n"
        "def process(data: str | None = None) -> list[str]:\n"
        "    items: dict[str, int] = {}\n"
        "    return []\n"
    )
    with TemporaryDirectory():
        result, changes = Codemods.modernize_type_annotations(body, "m.py")
        assert len(changes) == 0
        assert result == body


def test_validator_inline_import() -> None:
    """Validator flags imports inside functions."""
    body: str = (
        "#!/usr/bin/env python3\n"
        "# m.py\n"
        "def f() -> None:\n"
        "    import os\n"
        "    print(os.getcwd())\n"
    )
    with TemporaryDirectory() as tmp:
        report: ValidationReport = PythonProValidator.validate(
            _write(tmp, "m.py", body),
        )
        rules: set[str] = {i.rule for i in report.issues}
        assert "inline_import" in rules


def test_validator_print_usage() -> None:
    """Validator flags print() usage."""
    body: str = (
        "#!/usr/bin/env python3\n"
        "# m.py\n"
        "def f() -> None:\n"
        "    print('hello')\n"
    )
    with TemporaryDirectory() as tmp:
        report: ValidationReport = PythonProValidator.validate(
            _write(tmp, "m.py", body),
        )
        rules: set[str] = {i.rule for i in report.issues}
        assert "print_usage" in rules


_TESTS: Final[tuple[Callable[[], None], ...]] = (
    test_parser_ruff,
    test_models_total,
    test_validator_flags_missing_shebang,
    test_validator_docstring_public_only,
    test_annotation_reporter_no_write,
    test_detector_async,
    test_codemods_insert_header_and_future,
    test_codemods_slots_return_none_import,
    test_semantic_cache_roundtrip,
    test_validator_broad_except_assert_raisefrom,
    test_codemod_matchcase_conversion,
    test_codemod_matchcase_no_conversion,
    test_codemod_type_annotations,
    test_codemod_type_annotations_idempotent,
    test_validator_inline_import,
    test_validator_print_usage,
)


def run() -> int:
    """Run every test; return a process exit code."""
    failed: int = 0
    test: Callable[[], None]
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
