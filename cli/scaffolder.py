#!/usr/bin/env python3
# cli/scaffolder.py — Generate python-pro-conformant code skeletons.

from __future__ import annotations

from typing import Final

_MODULE: Final[str] = """#!/usr/bin/env python3
# __PATH__

from __future__ import annotations


class __CLASS__:
    \"\"\"TODO: describe __CLASS__.\"\"\"

    __slots__: tuple[str, ...] = ()
"""

_SERVICE: Final[str] = """#!/usr/bin/env python3
# __PATH__

from __future__ import annotations


class __CLASS__Service:
    \"\"\"Application service for __SLUG__.\"\"\"

    __slots__: tuple[str, ...] = ()

    async def execute(self) -> None:
        \"\"\"Run the service action.\"\"\"
        raise NotImplementedError
"""

_FASTAPI_ROUTER: Final[str] = """#!/usr/bin/env python3
# __PATH__

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

router: APIRouter = APIRouter(prefix="/__SLUG__", tags=["__SLUG__"])


class __CLASS__In(BaseModel):
    \"\"\"Request body for creating a __CLASS__.\"\"\"

    name: str


class __CLASS__Out(BaseModel):
    \"\"\"Response body for a __CLASS__.\"\"\"

    id: int
    name: str


@router.get("/{item_id}", response_model=__CLASS__Out)
async def get___SLUG__(item_id: int) -> __CLASS__Out:
    \"\"\"Return a single __SLUG__ by id.\"\"\"
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")


@router.post("", response_model=__CLASS__Out, status_code=status.HTTP_201_CREATED)
async def create___SLUG__(payload: __CLASS__In) -> __CLASS__Out:
    \"\"\"Create a __SLUG__.\"\"\"
    raise NotImplementedError
"""

_SQLALCHEMY_MODEL: Final[str] = """#!/usr/bin/env python3
# __PATH__

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    \"\"\"Declarative base for ORM models.\"\"\"


class __CLASS__(Base):
    \"\"\"ORM model for __SLUG__.\"\"\"

    __tablename__ = "__SLUG__"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
"""

_PYDANTIC_MODEL: Final[str] = """#!/usr/bin/env python3
# __PATH__

from __future__ import annotations

from pydantic import BaseModel, Field


class __CLASS__(BaseModel):
    \"\"\"__CLASS__ schema.\"\"\"

    id: int
    name: str = Field(min_length=1, max_length=255)
"""

_PYTEST: Final[str] = """#!/usr/bin/env python3
# __PATH__

from __future__ import annotations

from pytest import mark


@mark.parametrize(("given", "expected"), [(1, 1)])
def test___SLUG__(given: int, expected: int) -> None:
    \"\"\"__SLUG__ returns the expected value.\"\"\"
    assert given == expected
"""


class Scaffolder:
    """Produces standard-conformant skeletons for common Python artefacts."""

    __slots__: tuple[str, ...] = ()

    KINDS: Final[tuple[str, ...]] = (
        "module",
        "service",
        "fastapi_router",
        "sqlalchemy_model",
        "pydantic_model",
        "pytest",
    )

    @staticmethod
    def _pascal(name: str) -> str:
        """Convert an arbitrary name to PascalCase."""
        parts: list[str] = [
            p for p in name.replace("-", " ").replace("_", " ").split() if p
        ]
        return "".join(part[:1].upper() + part[1:] for part in parts) or "Thing"

    @staticmethod
    def _slug(name: str) -> str:
        """Convert an arbitrary name to a snake_case slug."""
        parts: list[str] = [
            p for p in name.replace("-", " ").replace("_", " ").split() if p
        ]
        return "_".join(part.lower() for part in parts) or "thing"

    @classmethod
    def _fill(cls, template: str, cls_name: str, slug: str) -> str:
        """Substitute placeholders in a template."""
        return (
            template.replace("__CLASS__", cls_name)
            .replace("__SLUG__", slug)
            .replace("__PATH__", f"{slug}.py")
        )

    @classmethod
    def generate(cls, kind: str, name: str) -> str:
        """Return a python-pro-conformant skeleton for `kind` named `name`."""
        cls_name: str = cls._pascal(name)
        slug: str = cls._slug(name)
        template: str
        match kind:
            case "module":
                template = _MODULE
            case "service":
                template = _SERVICE
                cls_name = cls_name.removesuffix("Service")
            case "fastapi_router":
                template = _FASTAPI_ROUTER
            case "sqlalchemy_model":
                template = _SQLALCHEMY_MODEL
            case "pydantic_model":
                template = _PYDANTIC_MODEL
            case "pytest":
                template = _PYTEST
            case _:
                return f"unknown kind '{kind}'. options: {', '.join(cls.KINDS)}"
        return cls._fill(template, cls_name, slug)
