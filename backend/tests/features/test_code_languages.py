"""Tests for multi-language sandbox configuration."""

from __future__ import annotations

import pytest

from app.features.code import tool
from app.features.code.languages import (
    build_runner_script,
    generator_system_prompt,
    get_language_config,
    normalize_language,
)
from app.features.code.schemas import ExecutionOutcome, TestCaseDTO


def test_normalize_language_aliases():
    assert normalize_language("py") == "python"
    assert normalize_language("js") == "javascript"
    assert normalize_language("JavaScript") == "javascript"


def test_normalize_language_rejects_unknown():
    with pytest.raises(ValueError, match="Unsupported language"):
        normalize_language("rust")


def test_javascript_runner_uses_node():
    config, runner = build_runner_script("javascript")
    assert config.run_command == "node /home/user/runner.js"
    assert "module.exports" in runner
    assert "console.log(JSON.stringify(results))" in runner


def test_generator_prompt_mentions_javascript():
    prompt = generator_system_prompt("javascript")
    assert "JavaScript" in prompt
    assert "module.exports" in prompt


@pytest.mark.asyncio
async def test_execute_submission_rejects_unknown_language():
    outcome, results, error = await tool.execute_submission(
        "export {}",
        [TestCaseDTO(id="1", input="x", expected_output="y")],
        language="rust",
    )
    assert outcome == ExecutionOutcome.SANDBOX_ERROR
    assert results == []
    assert error is not None
    assert "Unsupported" in error


def test_get_language_config_python():
    config = get_language_config("python")
    assert config.solution_filename == "solution.py"
