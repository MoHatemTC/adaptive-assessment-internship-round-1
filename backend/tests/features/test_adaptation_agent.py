"""
test_adaptation_agent.py
Unit tests for app/features/adaptation/agent.py — fully mocked LLM, no DB/network.

Covers:
  1. happy path     — mixed-tool answers produce valid AdaptationResult
  2. empty input    — raises ValueError
  3. bad LLM output — invalid next_difficulty falls back to score-based rule
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.adaptation.agent import run_adaptation, _score_to_difficulty
from app.features.adaptation.schemas import AnswerRecord


SESSION_ID = uuid.uuid4()


def _mock_llm_gateway(payload: dict):
    """Patch get_llm_with_tracing to return a bound LLM with ainvoke stub."""
    response = MagicMock()
    response.content = json.dumps(payload)

    bound = MagicMock()
    bound.ainvoke = AsyncMock(return_value=response)
    bound.bind.return_value = bound

    llm = MagicMock()
    llm.bind.return_value = bound

    return patch(
        "app.features.adaptation.agent.get_llm_with_tracing",
        return_value=(llm, []),
    )


VALID_PAYLOAD = {
    "dimension_scores": {
        "thinking":   {"score": 7, "feedback": "Strong reasoning."},
        "soft":       {"score": 5, "feedback": "Could be clearer."},
        "work":       {"score": 6, "feedback": "Mostly correct."},
        "digital_ai": {"score": 8, "feedback": "Good vocabulary."},
        "growth":     {"score": 4, "feedback": "Inconsistent."},
    },
    "next_difficulty": "hard",
}


# ---------------------------------------------------------------------------
# 1. Happy path — mixed tools
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_adaptation_mixed_tools_returns_valid_result():
    answers = [
        AnswerRecord(tool="diagram", dimension="digital_ai", score=0.8, feedback="Good diagram read."),
        AnswerRecord(tool="mcq",     dimension="thinking",   score=1.0, feedback="All correct."),
        AnswerRecord(tool="voice",   dimension="soft",        score=0.6, feedback="Clear but brief."),
    ]

    with _mock_llm_gateway(VALID_PAYLOAD):
        result = await run_adaptation(SESSION_ID, answers)

    assert result.session_id == SESSION_ID
    assert result.next_difficulty == "hard"
    assert set(result.dimension_scores.keys()) == {
        "thinking", "soft", "work", "digital_ai", "growth"
    }
    assert result.dimension_scores["thinking"].score == 7
    assert all(1 <= d.score <= 10 for d in result.dimension_scores.values())


# ---------------------------------------------------------------------------
# 2. Empty input
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_adaptation_empty_answers_raises():
    with pytest.raises(ValueError, match="No answers provided"):
        await run_adaptation(SESSION_ID, [])


# ---------------------------------------------------------------------------
# 3. Invalid next_difficulty falls back to score-based rule
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_adaptation_invalid_difficulty_falls_back():
    bad_payload = {**VALID_PAYLOAD, "next_difficulty": "extreme"}  # not a valid enum value
    answers = [AnswerRecord(tool="mcq", dimension="thinking", score=0.9, feedback="Good.")]

    with _mock_llm_gateway(bad_payload):
        result = await run_adaptation(SESSION_ID, answers)

    # avg of (7,5,6,8,4) = 6.0 -> falls in medium band (<=6)
    assert result.next_difficulty == "medium"


# ---------------------------------------------------------------------------
# Pure function test — no mocking needed
# ---------------------------------------------------------------------------

def test_score_to_difficulty_bands():
    assert _score_to_difficulty({"a": {"score": 2}, "b": {"score": 3}}) == "easy"     # avg 2.5
    assert _score_to_difficulty({"a": {"score": 5}, "b": {"score": 6}}) == "medium"   # avg 5.5
    assert _score_to_difficulty({"a": {"score": 9}, "b": {"score": 8}}) == "hard"     # avg 8.5
