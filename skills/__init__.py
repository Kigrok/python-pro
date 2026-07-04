#!/usr/bin/env python3
# skills/__init__.py — Skill modules for python-pro.

from skills.detector import CodeAnalyzer, SkillDetector

__all__: list[str] = [
    "CodeAnalyzer",
    "SkillDetector",
]
