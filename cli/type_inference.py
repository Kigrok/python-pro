#!/usr/bin/env python3
# cli/type_inference.py — Infer types from code usage patterns.

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

# Common type inference patterns.
_TYPE_MAP: Final[dict[str, str]] = {
    "len": "int",
    "int": "int",
    "float": "float",
    "str": "str",
    "bool": "bool",
    "list": "list",
    "dict": "dict",
    "set": "set",
    "tuple": "tuple",
    "type": "type",
    "isinstance": "bool",
    "hasattr": "bool",
    "getattr": "object",
    "sorted": "list",
    "reversed": "list",
    "enumerate": "tuple",
    "zip": "list",
    "map": "list",
    "filter": "list",
    "range": "range",
    "open": "IO",
    "Path": "Path",
}


@dataclass(slots=True)
class TypeHint:
    """Inferred type hint for a variable or return value."""

    name: str
    inferred_type: str
    confidence: float  # 0.0 to 1.0
    source: str  # "assignment", "call", "annotation", "usage"

    def __str__(self) -> str:
        return f"{self.name}: {self.inferred_type} ({self.confidence:.0%} from {self.source})"


@dataclass(slots=True)
class InferenceResult:
    """Type inference results for a file."""

    file: str
    variables: list[TypeHint] = field(default_factory=list)
    functions: list[TypeHint] = field(default_factory=list)
    missing_annotations: list[str] = field(default_factory=list)

    def to_compact(self) -> str:
        parts: list[str] = [f"{self.file}:"]
        if self.variables:
            parts.append(f"  variables: {len(self.variables)} inferred")
        if self.functions:
            parts.append(f"  functions: {len(self.functions)} inferred")
        if self.missing_annotations:
            parts.append(f"  missing annotations: {len(self.missing_annotations)}")
        return "\n".join(parts)


class TypeInferencer:
    """AST-based type inference from code patterns."""

    __slots__: tuple[str, ...] = ()

    @staticmethod
    def infer_from_assignment(node: ast.Assign) -> TypeHint | None:
        """Infer type from assignment pattern."""
        if not isinstance(node.targets[0], ast.Name):
            return None

        name = node.targets[0].id
        value = node.value

        # Direct constant.
        if isinstance(value, ast.Constant):
            const_type = type(value.value).__name__
            return TypeHint(
                name=name,
                inferred_type=const_type,
                confidence=1.0,
                source="assignment",
            )

        # List literal.
        if isinstance(value, ast.List):
            if value.elts:
                inner = TypeInferencer._infer_expr_type(value.elts[0])
                return TypeHint(
                    name=name,
                    inferred_type=f"list[{inner}]",
                    confidence=0.8,
                    source="assignment",
                )
            return TypeHint(
                name=name, inferred_type="list", confidence=0.9, source="assignment"
            )

        # Dict literal.
        if isinstance(value, ast.Dict):
            return TypeHint(
                name=name, inferred_type="dict", confidence=0.9, source="assignment"
            )

        # Set literal.
        if isinstance(value, ast.Set):
            return TypeHint(
                name=name, inferred_type="set", confidence=0.9, source="assignment"
            )

        # Call expression.
        if isinstance(value, ast.Call):
            return TypeInferencer._infer_from_call(name, value)

        # Name reference.
        if isinstance(value, ast.Name):
            return TypeHint(
                name=name,
                inferred_type=f"SameType as {value.id}",
                confidence=0.5,
                source="usage",
            )

        return None

    @staticmethod
    def _infer_from_call(name: str, call: ast.Call) -> TypeHint:
        """Infer type from function call."""
        if isinstance(call.func, ast.Name):
            func_name = call.func.id
            if func_name in _TYPE_MAP:
                return TypeHint(
                    name=name,
                    inferred_type=_TYPE_MAP[func_name],
                    confidence=0.8,
                    source="call",
                )
        if isinstance(call.func, ast.Attribute):
            method = call.func.attr
            if method in ("append", "extend", "insert"):
                return TypeHint(
                    name=name, inferred_type="None", confidence=0.9, source="call"
                )
            if method == "items":
                return TypeHint(
                    name=name,
                    inferred_type="list[tuple]",
                    confidence=0.8,
                    source="call",
                )
            if method == "values":
                return TypeHint(
                    name=name, inferred_type="list", confidence=0.7, source="call"
                )
            if method == "keys":
                return TypeHint(
                    name=name, inferred_type="list", confidence=0.7, source="call"
                )
            if method == "strip":
                return TypeHint(
                    name=name, inferred_type="str", confidence=0.9, source="call"
                )
            if method == "join":
                return TypeHint(
                    name=name, inferred_type="str", confidence=0.9, source="call"
                )
            if method == "split":
                return TypeHint(
                    name=name, inferred_type="list[str]", confidence=0.9, source="call"
                )
            if method == "read":
                return TypeHint(
                    name=name,
                    inferred_type="str | bytes",
                    confidence=0.7,
                    source="call",
                )
            if method == "get":
                return TypeHint(
                    name=name, inferred_type="object", confidence=0.5, source="call"
                )
        return TypeHint(
            name=name, inferred_type="object", confidence=0.3, source="call"
        )

    @staticmethod
    def _infer_expr_type(node: ast.expr) -> str:
        """Infer type of an expression node."""
        if isinstance(node, ast.Constant):
            return type(node.value).__name__
        if isinstance(node, ast.List):
            return "list"
        if isinstance(node, ast.Dict):
            return "dict"
        if isinstance(node, ast.Set):
            return "set"
        if isinstance(node, ast.Tuple):
            return "tuple"
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return _TYPE_MAP.get(node.func.id, "object")
        return "object"

    @staticmethod
    def infer_from_return(node: ast.Return) -> TypeHint | None:
        """Infer return type from return statement."""
        if node.value is None:
            return TypeHint(
                name="return", inferred_type="None", confidence=1.0, source="return"
            )
        inferred = TypeInferencer._infer_expr_type(node.value)
        return TypeHint(
            name="return",
            inferred_type=inferred,
            confidence=0.7,
            source="return",
        )

    @staticmethod
    def analyze(file_path: str) -> InferenceResult:
        """Analyze file and infer types."""
        try:
            source = Path(file_path).read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=file_path)
        except (OSError, SyntaxError):
            return InferenceResult(file=file_path)

        result = InferenceResult(file=file_path)

        for node in ast.walk(tree):
            # Variable assignments.
            if isinstance(node, ast.Assign):
                hint = TypeInferencer.infer_from_assignment(node)
                if hint:
                    result.variables.append(hint)

            # Function definitions.
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check if return annotation exists.
                has_return_annotation = node.returns is not None

                # Infer from returns.
                for child in ast.walk(node):
                    if isinstance(child, ast.Return):
                        hint = TypeInferencer.infer_from_return(child)
                        if hint and not has_return_annotation:
                            result.functions.append(
                                TypeHint(
                                    name=node.name,
                                    inferred_type=f"-> {hint.inferred_type}",
                                    confidence=hint.confidence,
                                    source="return",
                                )
                            )

                # Check for missing annotations.
                if not has_return_annotation:
                    result.missing_annotations.append(f"{node.name}() return type")

                # Check argument annotations.
                for arg in node.args.args:
                    if arg.arg != "self" and arg.annotation is None:
                        result.missing_annotations.append(f"{node.name}().{arg.arg}")

        return result
