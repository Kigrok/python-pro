#!/usr/bin/env python3
# mcp_server/__init__.py — MCP server package for python-pro.

__all__: list[str] = ["app"]


def __getattr__(name: str) -> object:
    """Expose `app` lazily so `python -m mcp_server.server` skips a double import."""
    if name == "app":
        from mcp_server.server import app

        return app
    raise AttributeError(name)
