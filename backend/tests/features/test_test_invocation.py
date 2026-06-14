"""Tests for safe test-case invocation normalization."""

import pytest

from app.features.code.test_invocation import InvocationParseError, normalize_test_invocation


def test_normalize_structured_json():
    raw = '{"args": ["hello"], "kwargs": {}, "stdout": true}'
    inv = normalize_test_invocation(raw)
    assert inv["args"] == ["hello"]
    assert inv["stdout"] is True


def test_normalize_legacy_print_solution():
    inv = normalize_test_invocation("print(solution('hello'))")
    assert inv["args"] == ["hello"]
    assert inv["stdout"] is True
    assert inv["unpack"] is False


def test_normalize_legacy_unpack():
    inv = normalize_test_invocation("print(*solution([2, 7], 9))")
    assert inv["args"] == [[2, 7], 9]
    assert inv["unpack"] is True


def test_rejects_arbitrary_exec():
    with pytest.raises(InvocationParseError):
        normalize_test_invocation("import os; os.system('rm -rf /')")


def test_normalize_legacy_console_solution():
    inv = normalize_test_invocation(
        'console.log(solution("hello"))',
        language="javascript",
    )
    assert inv["args"] == ["hello"]
    assert inv["stdout"] is True


def test_normalize_legacy_console_unpack():
    inv = normalize_test_invocation(
        "console.log(...solution([2, 7], 9))",
        language="javascript",
    )
    assert inv["args"] == [[2, 7], 9]
    assert inv["unpack"] is True
