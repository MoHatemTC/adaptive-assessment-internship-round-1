"""Tests for the blueprint planner agent.

LLM calls are mocked so the suite runs without an API key. Covers the happy
path, malformed output, and Kimi K2's list-of-blocks response shape.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.nodes import blueprint as planner_mod
from app.agent.nodes.blueprint import run_planner
from app.shared.schemas.blueprint import Blueprint


def _valid_blueprint_json() -> str:
    """Return a valid serialized blueprint for an mcq+voice assessment."""
    return json.dumps(
        {
            "title": "Backend Engineer Screen",
            "description": "Assesses backend fundamentals.",
            "tools": {
                "mcq": {
                    "enabled": True,
                    "question_count": 3,
                    "min_difficulty": "beginner",
                    "max_difficulty": "advanced",
                    "time_limit_seconds": None,
                },
                "voice": {
                    "enabled": True,
                    "question_count": 2,
                    "min_difficulty": "beginner",
                    "max_difficulty": "intermediate",
                    "time_limit_seconds": 180,
                },
            },
            "skill_dimensions": ["thinking", "work"],
            "total_questions": 5,
        }
    )


def _mock_llm(content: object) -> MagicMock:
    """Return a mock LLM whose ``ainvoke`` yields ``content``."""
    llm = MagicMock()
    llm.temperature = 0.1
    response = MagicMock()
    response.content = content
    llm.ainvoke = AsyncMock(return_value=response)
    return llm


@pytest.mark.asyncio
async def test_planner_returns_valid_blueprint():
    llm = _mock_llm(_valid_blueprint_json())
    with patch.object(planner_mod, "get_llm_with_tracing", return_value=(llm, [])):
        blueprint = await run_planner("Test backend skills", ["mcq", "voice"])

    assert isinstance(blueprint, Blueprint)
    assert blueprint.total_questions == 5
    assert blueprint.enabled_tools() == ["mcq", "voice"]


@pytest.mark.asyncio
async def test_planner_handles_malformed_llm_response():
    llm = _mock_llm("this is not json at all")
    with patch.object(planner_mod, "get_llm_with_tracing", return_value=(llm, [])):
        with pytest.raises(ValueError):
            await run_planner("anything", ["mcq"])


@pytest.mark.asyncio
async def test_planner_handles_kimi_k2_list_response():
    content = [
        {"type": "thinking", "thinking": "deciding the tool mix..."},
        {"type": "thinking", "thinking": "finalizing counts..."},
        _valid_blueprint_json(),
    ]
    llm = _mock_llm(content)
    with patch.object(planner_mod, "get_llm_with_tracing", return_value=(llm, [])):
        blueprint = await run_planner("Test backend skills", ["mcq", "voice"])

    assert isinstance(blueprint, Blueprint)
    assert blueprint.total_questions == 5
    assert blueprint.enabled_tools() == ["mcq", "voice"]
