"""Normalize test-case inputs into a safe function-call contract for the sandbox runner."""

from __future__ import annotations

import ast
import json
import re
from typing import Any

from app.features.code.constants import SupportedLanguage, validate_language

class InvocationParseError(ValueError):
    """Raised when a test case input cannot be converted to a safe invocation."""


def _literal_from_ast(node: ast.AST) -> Any:
    """Extract compile-time literals only — no names, calls, or attribute access."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [_literal_from_ast(elt) for elt in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_literal_from_ast(elt) for elt in node.elts)
    if isinstance(node, ast.Dict):
        return {
            _literal_from_ast(key): _literal_from_ast(value)
            for key, value in zip(node.keys, node.values, strict=False)
        }
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _literal_from_ast(node.operand)
        if isinstance(value, (int, float)):
            return -value
    raise InvocationParseError(f"Unsupported expression in test input: {ast.dump(node)}")


def _parse_legacy_print_solution(raw: str) -> dict[str, Any]:
    """Parse ``print(solution(...))`` / ``print(*solution(...))`` without executing code."""
    stripped = raw.strip()
    if not stripped:
        raise InvocationParseError("Empty test input")

    tree = ast.parse(stripped, mode="exec")
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.Expr):
        raise InvocationParseError("Test input must be a single print(solution(...)) statement")

    print_call = tree.body[0].value
    if not isinstance(print_call, ast.Call):
        raise InvocationParseError("Test input must call print(...)")
    if not isinstance(print_call.func, ast.Name) or print_call.func.id != "print":
        raise InvocationParseError("Test input must use print(...)")
    if len(print_call.args) != 1:
        raise InvocationParseError("print(...) must have exactly one argument")

    unpack = False
    inner = print_call.args[0]
    if isinstance(inner, ast.Starred):
        unpack = True
        inner = inner.value

    if not isinstance(inner, ast.Call):
        raise InvocationParseError("print argument must call solution(...)")
    if not isinstance(inner.func, ast.Name) or inner.func.id != "solution":
        raise InvocationParseError("Only solution(...) calls are permitted in legacy test inputs")

    args = [_literal_from_ast(arg) for arg in inner.args]
    kwargs = {
        kw.arg: _literal_from_ast(kw.value)
        for kw in inner.keywords
        if kw.arg is not None
    }
    return {"args": args, "kwargs": kwargs, "stdout": True, "unpack": unpack}


def _parse_legacy_console_solution(raw: str) -> dict[str, Any]:
    """Parse ``console.log(solution(...))`` by translating to Python print AST rules."""
    stripped = raw.strip()
    if not stripped:
        raise InvocationParseError("Empty test input")

    py_equivalent = re.sub(
        r"console\.log\(\s*\.\.\.\s*solution\s*\(",
        "print(*solution(",
        stripped,
    )
    py_equivalent = re.sub(r"^console\.log\s*\(", "print(", py_equivalent)
    if py_equivalent == stripped:
        raise InvocationParseError("Test input must be console.log(solution(...))")
    return _parse_legacy_print_solution(py_equivalent)


def _parse_structured_json(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvocationParseError(f"Invalid JSON test input: {exc}") from exc
    if not isinstance(data, dict) or "args" not in data:
        raise InvocationParseError("Structured test input must be a JSON object with an 'args' key")
    return {
        "args": data.get("args", []),
        "kwargs": data.get("kwargs", {}),
        "stdout": bool(data.get("stdout", True)),
        "unpack": bool(data.get("unpack", False)),
    }


def normalize_test_invocation(
    raw: str,
    *,
    language: str | SupportedLanguage = SupportedLanguage.PYTHON,
) -> dict[str, Any]:
    """Convert stored test input to a JSON-serializable invocation dict for the sandbox runner.

    Supported formats:
    - Structured JSON: ``{"args": [...], "kwargs": {...}, "stdout": true, "unpack": false}``
    - Legacy Python (read-only AST): ``print(solution('x'))`` or ``print(*solution(a, b))``
    - Legacy JavaScript: ``console.log(solution('x'))`` or ``console.log(...solution(a, b))``
    """
    lang = language if isinstance(language, SupportedLanguage) else validate_language(str(language))
    stripped = raw.strip()
    if stripped.startswith("{"):
        return _parse_structured_json(stripped)

    if lang in (SupportedLanguage.JAVASCRIPT, SupportedLanguage.TYPESCRIPT):
        return _parse_legacy_console_solution(stripped)
    return _parse_legacy_print_solution(stripped)
