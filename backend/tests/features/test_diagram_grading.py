import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.features.diagram.grading import (
    DiagramToolOutput,
    GradeResult,
    JudgeVerdict,
    Rubric,
    _call_grader,
    _validate_scores,
    grade_visual_answer,
)


def make_answer():
    return DiagramToolOutput(
        session_id="s1", question_id="q1", image_url="http://img",
        raw_answer_text="The bottleneck is the DB.", timestamp=datetime.now(timezone.utc),
    )


def make_rubric():
    return Rubric(rubric_id="r1", question_id="q1", criteria_text="...",
                   dimension_weights={"thinking": 0.6, "digital_ai": 0.4})


def test_validate_scores_drops_unknown_dim_and_clamps():
    rubric = make_rubric()
    out = _validate_scores({"thinking": 1.5, "growth": 0.9, "digital_ai": -0.2}, rubric)
    assert out == {"thinking": 1.0, "digital_ai": 0.0}  # growth dropped, others clamped


@pytest.mark.asyncio
async def test_grade_visual_answer_pass(monkeypatch):
    grader_resp = {"dimension_scores": {"thinking": 0.7}, "reasoning": "ok", "confidence": 0.8}
    judge_resp = {"verdict": "pass", "notes": "consistent"}

    with patch("app.features.diagram.grading._call_grader", AsyncMock(return_value=grader_resp)), \
         patch("app.features.diagram.grading._call_judge", AsyncMock(return_value=judge_resp)):
        result = await grade_visual_answer(make_rubric(), make_answer())

    assert isinstance(result, GradeResult)
    assert result.is_trusted is True
    assert result.dimension_scores == {"thinking": 0.7}
    assert result.judge_verdict is JudgeVerdict.PASS


@pytest.mark.asyncio
async def test_grade_visual_answer_judge_fails():
    grader_resp = {"dimension_scores": {"thinking": 0.9}, "reasoning": "shaky", "confidence": 0.4}
    judge_resp = {"verdict": "fail", "notes": "hallucinated claim"}

    with patch("app.features.diagram.grading._call_grader", AsyncMock(return_value=grader_resp)), \
         patch("app.features.diagram.grading._call_judge", AsyncMock(return_value=judge_resp)):
        result = await grade_visual_answer(make_rubric(), make_answer())

    assert result.is_trusted is False
    assert result.judge_verdict is JudgeVerdict.FAIL


@pytest.mark.asyncio
async def test_call_grader_uses_kernel_gateway():
    payload = {
        "dimension_scores": {"thinking": 0.6},
        "reasoning": "partial",
        "confidence": 0.7,
    }
    response = MagicMock()
    response.content = json.dumps(payload)
    bound = MagicMock()
    bound.ainvoke = AsyncMock(return_value=response)
    llm = MagicMock()
    llm.bind.return_value = bound

    with patch(
        "app.features.diagram.grading.get_llm_with_tracing",
        return_value=(llm, []),
    ):
        result = await _call_grader(make_rubric(), make_answer())

    assert result == payload
    bound.ainvoke.assert_awaited_once()