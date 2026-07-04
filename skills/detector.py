#!/usr/bin/env python3
# skills/detector.py — Auto-detect active skills based on code patterns.

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Final


class SkillDetector:
    """Detects which skills to activate based on code patterns."""

    __slots__: tuple[str, ...] = ()

    PATTERNS: Final[dict[str, list[str]]] = {
        "async": [
            "import asyncio",
            "from asyncio",
            "async def",
            "await ",
            "asyncio.gather",
            "asyncio.create_task",
            "asyncio.Semaphore",
            "asyncio.TaskGroup",
        ],
        "http": [
            "import aiohttp",
            "from aiohttp",
            "import httpx",
            "from httpx",
            "import curl_cffi",
            "from curl_cffi",
            "ClientSession",
            "AsyncClient",
            ".get(",
            ".post(",
            ".request(",
        ],
        "database": [
            "import sqlalchemy",
            "from sqlalchemy",
            "import asyncpg",
            "from asyncpg",
            "AsyncSession",
            "select(",
            "session.execute",
            "session.add(",
            "session.query",
            "create_async_engine",
        ],
        "patterns": [
            "Protocol",
            "Factory",
            "Builder",
            "Observer",
            "Strategy",
            "Singleton",
            "Proxy",
        ],
        "fastapi": [
            "from fastapi",
            "import fastapi",
            "APIRouter",
            "FastAPI(",
            "Depends(",
            "@router.",
            "@app.get",
            "@app.post",
            "HTTPException",
        ],
        "pydantic": [
            "from pydantic",
            "import pydantic",
            "BaseModel",
            "Field(",
            "field_validator",
            "model_validator",
            "ConfigDict",
        ],
        "security": [
            "eval(",
            "exec(",
            "subprocess",
            "os.system",
            "pickle.loads",
            "yaml.load",
            "hashlib.md5",
            "hashlib.sha1",
            "shell=True",
        ],
        "testing": [
            "import pytest",
            "from pytest",
            "def test_",
            "parametrize",
            "pytest.fixture",
            "pytest.raises",
        ],
        "errors": [
            "raise ",
            "except ",
            "try:",
            "finally:",
            "contextlib",
        ],
        "logging": [
            "import logging",
            "from logging",
            "getLogger",
            "logging.getLogger",
            "logger.",
            "NullHandler",
            "LoggerAdapter",
        ],
        "dependencies": [
            "import requests",
            "from requests",
            "import pytz",
            "from pytz",
            "import toml",
            "import simplejson",
            "import ujson",
            "import dateutil",
            "from dateutil",
            "import six",
            "import attr",
            "from attr",
            "import click",
            "from click",
            "import typer",
        ],
        "control_flow": [
            "match ",
            "case ",
            ":=",
            "except*",
            "ExceptionGroup",
        ],
        "data_structures": [
            "@dataclass",
            "deque",
            "heapq",
            "OrderedDict",
            "defaultdict",
            "Counter",
            "bisect",
            "NamedTuple",
        ],
        "modern_python": [
            "TypeAlias",
            "StrEnum",
            "IntEnum",
            "Self",
            "override",
            "tomllib",
            "TaskGroup",
        ],
        "style": [
            "# noqa",
            "TODO",
            "FIXME",
            "__all__",
        ],
        "typing": [
            "TypeVar",
            "ParamSpec",
            "Protocol",
            "TypedDict",
            "Literal[",
            "Annotated[",
            "cast(",
            "overload",
        ],
        "performance": [
            "@timed",
            "@track_memory",
            "lru_cache",
            "@cache",
            "tracemalloc",
            "format_bytes",
            "object_weight",
            "profile_call",
            "get_timing_stats",
            "get_memory_stats",
        ],
        "memory": [
            "__slots__",
            "Generator",
            "yield ",
            "frozenset",
            "Final[",
            "cached_property",
            "lru_cache",
            "@cache",
            "bytearray",
            "array(",
        ],
        "cpython_patterns": [
            "__all__",
            "_sentinel",
            "__init_subclass__",
            "__class_getitem__",
            "__set_name__",
            "__slots__",
            "ClassVar",
            "TypeAlias",
            "Protocol",
            "Literal[",
            "singledispatch",
            "total_ordering",
        ],
    }

    @classmethod
    def detect(cls, file_path: str) -> list[str]:
        """Detect which skills are relevant for a file."""
        try:
            content: str = Path(file_path).read_text()
        except (OSError, UnicodeDecodeError):
            return []

        active_skills: list[str] = []
        skill_name: str
        keywords: list[str]
        for skill_name, keywords in cls.PATTERNS.items():
            keyword: str
            for keyword in keywords:
                if keyword in content:
                    active_skills.append(skill_name)
                    break

        return active_skills

    @staticmethod
    def _digest(markdown: str) -> str:
        """Keep only rule lines (headings and bullets); drop prose and code blocks."""
        kept: list[str] = []
        in_code: bool = False
        line: str
        for line in markdown.splitlines():
            stripped: str = line.strip()
            if stripped.startswith("```"):
                in_code = not in_code
                continue
            if in_code or not stripped:
                continue
            if stripped.startswith(("-", "*", "#")):
                kept.append(stripped)
        return "\n".join(kept)

    @classmethod
    def get_rules(cls, skills: list[str]) -> str:
        """Get a condensed, token-frugal rule digest for active skills."""
        rules_dir: Path = Path(__file__).parent.parent / "skills"
        combined: list[str] = []

        skill: str
        for skill in skills:
            skill_file: Path = rules_dir / f"{skill}.md"
            if not skill_file.exists():
                continue
            digest: str = _cached_digest(skill_file)
            if digest:
                combined.append(digest)
                combined.append("")

        return "\n".join(combined)


@lru_cache(maxsize=64)
def _cached_digest(skill_file: Path) -> str:
    """LRU-cached digest of a skill markdown file."""
    return SkillDetector._digest(skill_file.read_text())


class CodeAnalyzer:
    """Analyzes code and suggests improvements based on skills."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def analyze(file_path: str) -> dict[str, object]:
        """Analyze file and return skill recommendations."""
        skills: list[str] = SkillDetector.detect(file_path)
        rules: str = SkillDetector.get_rules(skills)

        return {
            "file": file_path,
            "active_skills": skills,
            "rules_count": len(rules.split("\n")),
            "has_async": "async" in skills,
            "has_http": "http" in skills,
            "has_database": "database" in skills,
            "has_patterns": "patterns" in skills,
            "has_fastapi": "fastapi" in skills,
            "has_pydantic": "pydantic" in skills,
            "has_security": "security" in skills,
            "has_testing": "testing" in skills,
            "has_errors": "errors" in skills,
            "has_logging": "logging" in skills,
            "has_dependencies": "dependencies" in skills,
            "has_performance": "performance" in skills,
            "has_memory": "memory" in skills,
            "has_cpython_patterns": "cpython_patterns" in skills,
        }
