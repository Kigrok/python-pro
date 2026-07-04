#!/usr/bin/env python3
# cli/codegen.py — Template-based code generation: boilerplate without AI tokens.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class GeneratedCode:
    """Result of code generation."""

    name: str
    kind: str  # module, class, function, test, schema, api
    source: str
    path: str = ""

    def to_compact(self) -> str:
        return f"[{self.kind}] {self.name}: {len(self.source.splitlines())} lines"


class TemplateEngine:
    """Generate Python code from templates."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def module(name: str, docstring: str = "") -> GeneratedCode:
        """Generate a conformant Python module."""
        doc = (
            f'"""{docstring or f"{name} module."}"""'
            if docstring
            else f'"""{name} module."""'
        )
        source = f'''#!/usr/bin/env python3
# {name}.py — {docstring or f"{name} module."}

from __future__ import annotations


{doc}


class _Config:
    """Module-level configuration."""

    __slots__: tuple[str, ...] = ()


def main() -> None:
    """Entry point."""
    pass


if __name__ == "__main__":
    main()
'''
        return GeneratedCode(name=name, kind="module", source=source)

    @staticmethod
    def dataclass_model(
        name: str, fields: dict[str, str] | None = None
    ) -> GeneratedCode:
        """Generate a dataclass model with __slots__."""
        fields = fields or {}
        field_lines = []
        for fname, ftype in fields.items():
            field_lines.append(f"    {fname}: {ftype}")

        if not field_lines:
            field_lines = ["    pass"]

        fields_str = "\n".join(field_lines)
        source = f'''#!/usr/bin/env python3
# {name.lower()}.py — Data model for {name}.

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class {name}:
    """Data model for {name}."""

{fields_str}
'''
        return GeneratedCode(name=name, kind="dataclass", source=source)

    @staticmethod
    def pydantic_model(
        name: str, fields: dict[str, str] | None = None
    ) -> GeneratedCode:
        """Generate a Pydantic model."""
        fields = fields or {}
        field_lines = []
        for fname, ftype in fields.items():
            field_lines.append(f"    {fname}: {ftype}")

        if not field_lines:
            field_lines = ["    pass"]

        fields_str = "\n".join(field_lines)
        source = f'''#!/usr/bin/env python3
# {name.lower()}.py — Pydantic model for {name}.

from __future__ import annotations

from pydantic import BaseModel


class {name}(BaseModel):
    """Pydantic model for {name}."""

{fields_str}
'''
        return GeneratedCode(name=name, kind="pydantic", source=source)

    @staticmethod
    def service(name: str, methods: list[str] | None = None) -> GeneratedCode:
        """Generate a service class."""
        methods = methods or ["process"]
        method_lines = []
        for m in methods:
            method_lines.append(
                f'''    async def {m}(self, **kwargs: object) -> dict[str, object]:
        """Execute {m}."""
        raise NotImplementedError
'''
            )

        methods_str = "\n".join(method_lines)
        source = f'''#!/usr/bin/env python3
# {name.lower()}.py — Service layer for {name}.

from __future__ import annotations

from typing import Final


class {name}Service:
    """Service layer for {name} operations."""

    __slots__: tuple[str, ...] = ()

{methods_str}
'''
        return GeneratedCode(name=f"{name}Service", kind="service", source=source)

    @staticmethod
    def test(name: str, target: str | None = None) -> GeneratedCode:
        """Generate a pytest test file."""
        target = target or name
        source = f'''#!/usr/bin/env python3
# test_{name.lower()}.py — Tests for {target}.

from __future__ import annotations

import pytest


class Test{name.title().replace("_", "")}:
    """Tests for {target}."""

    def test_basic(self) -> None:
        """Basic smoke test."""
        assert True

    def test_error_handling(self) -> None:
        """Test error cases."""
        with pytest.raises(ValueError):
            raise ValueError("test")
'''
        return GeneratedCode(name=f"test_{name}", kind="test", source=source)

    @staticmethod
    def api_router(name: str, endpoints: list[str] | None = None) -> GeneratedCode:
        """Generate a FastAPI router."""
        endpoints = endpoints or ["list", "create", "get", "update", "delete"]
        route_lines: list[str] = []
        for ep in endpoints:
            match ep:
                case "list":
                    route_lines.append(
                        f'@router.get("/{name.lower()}")\n'
                        f"async def list_{name}s() -> list[dict[str, object]]:\n"
                        f'    """List all {name}s."""\n'
                        f"    return []\n"
                    )
                case "create":
                    route_lines.append(
                        f'@router.post("/{name.lower()}")\n'
                        f"async def create_{name}(data: dict[str, object]) -> dict[str, object]:\n"
                        f'    """Create a new {name}."""\n'
                        f'    return {{"id": "1", **data}}\n'
                    )
                case "get":
                    route_lines.append(
                        f'@router.get("/{name.lower()}/{{item_id}}")\n'
                        f"async def get_{name}(item_id: str) -> dict[str, object]:\n"
                        f'    """Get a {name} by ID."""\n'
                        f'    return {{"id": item_id}}\n'
                    )
                case "update":
                    route_lines.append(
                        f'@router.put("/{name.lower()}/{{item_id}}")\n'
                        f"async def update_{name}(item_id: str, data: dict[str, object]) -> dict[str, object]:\n"
                        f'    """Update a {name}."""\n'
                        f'    return {{"id": item_id, **data}}\n'
                    )
                case "delete":
                    route_lines.append(
                        f'@router.delete("/{name.lower()}/{{item_id}}")\n'
                        f"async def delete_{name}(item_id: str) -> dict[str, str]:\n"
                        f'    """Delete a {name}."""\n'
                        f'    return {{"status": "deleted"}}\n'
                    )

        routes_str = "\n".join(route_lines)
        source = f"""#!/usr/bin/env python3
# {name.lower()}_router.py — FastAPI router for {name}.

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/{name.lower()}", tags=["{name}"])


{routes_str}
"""
        return GeneratedCode(name=f"{name}_router", kind="router", source=source)

    @staticmethod
    def sqlalchemy_model(
        name: str, fields: dict[str, str] | None = None
    ) -> GeneratedCode:
        """Generate a SQLAlchemy model."""
        fields = fields or {}
        col_lines = [
            f"    {fname} = Column({ftype})" for fname, ftype in fields.items()
        ]
        cols_str = "\n".join(col_lines)
        source = f'''#!/usr/bin/env python3
# {name.lower()}.py — SQLAlchemy model for {name}.

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class {name}(Base):
    """SQLAlchemy model for {name}."""

    __tablename__ = "{name.lower()}s"

    id = Column(Integer, primary_key=True, autoincrement=True)
{cols_str}
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )
'''
        return GeneratedCode(name=name, kind="sqlalchemy", source=source)

    @staticmethod
    def cli_command(name: str, description: str = "") -> GeneratedCode:
        """Generate a Typer CLI command."""
        source = f'''#!/usr/bin/env python3
# {name}.py — CLI command for {name}.

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(help="{description or name} command")
console = Console()


@app.command()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
) -> None:
    """Execute {name}."""
    if verbose:
        console.print(f"[bold green]Running {name}...[/]")
    console.print(f"[bold]{name} completed[/]")


if __name__ == "__main__":
    app()
'''
        return GeneratedCode(name=name, kind="cli", source=source)


class CodeGenEngine:
    """High-level code generation from specifications."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def from_spec(spec: dict[str, object]) -> GeneratedCode:
        """Generate code from a specification dict."""
        kind = str(spec.get("kind", "module"))
        name = str(spec.get("name", "generated"))
        fields = spec.get("fields")  # type: ignore
        methods = spec.get("methods")  # type: ignore
        endpoints = spec.get("endpoints")  # type: ignore

        match kind:
            case "module":
                return TemplateEngine.module(name, str(spec.get("docstring", "")))
            case "dataclass":
                return TemplateEngine.dataclass_model(name, fields)
            case "pydantic":
                return TemplateEngine.pydantic_model(name, fields)
            case "service":
                return TemplateEngine.service(name, methods)
            case "test":
                return TemplateEngine.test(name, str(spec.get("target", "")))
            case "router":
                return TemplateEngine.api_router(name, endpoints)
            case "sqlalchemy":
                return TemplateEngine.sqlalchemy_model(name, fields)
            case "cli":
                return TemplateEngine.cli_command(
                    name, str(spec.get("description", ""))
                )
            case _:
                return TemplateEngine.module(name)

    @staticmethod
    def batch(specs: list[dict[str, object]]) -> list[GeneratedCode]:
        """Generate multiple files from specs."""
        return [CodeGenEngine.from_spec(spec) for spec in specs]

    @staticmethod
    def write(generated: GeneratedCode, output_dir: str = ".") -> str:
        """Write generated code to file. Returns file path."""
        path = Path(output_dir) / f"{generated.name.replace('.', '/')}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(generated.source, encoding="utf-8")
        return str(path)
