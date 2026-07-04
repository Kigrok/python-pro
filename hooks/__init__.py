#!/usr/bin/env python3
# hooks/__init__.py — Hook entry points for python-pro.

from hooks.post_edit import main

__all__: list[str] = ["main"]
