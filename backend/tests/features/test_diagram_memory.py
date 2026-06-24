import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from app.features.diagram.grading import GradeResult, JudgeVerdict, Rubric
from app.features.diagram.evaluation_memory import build_memory_card, write_memory_card, grade_and_remember


def make_grade(verdict=JudgeVerdict.PASS):
    return GradeResult(
        session_id="s1", question_id="q1",
        dimension_scores={"thinking": 0.6}, reasoning="ok",
        grader_confidence=0.8, judge_verdict=verdict, judge_notes="",
    )


def make_rubric():
    return Rubric(rubric_id="r1", question_id="q1", criteria_text="...",
                   dimension_weights={"thinking": 1.0})


def test_build_memory_card_trusted():
    card = build_memory_card(make_grade(), make_rubric(), difficulty=4, topic_tags=("ds",))
    assert card is not None
    assert card.point_id == "s1:q1"
    assert card.dimension_scores == {"thinking": 0.6}


def test_build_memory_card_untrusted_returns_none():
    card = build_memory_card(make_grade(JudgeVerdict.FAIL), make_rubric(), 4, ("ds",))
    assert card is None


@pytest.mark.asyncio
async def test_write_memory_card_calls_upsert_with_payload():
    card = build_memory_card(make_grade(), make_rubric(), 4, ("ds",))
    writer = AsyncMock()
    embed_fn = lambda text: [0.1, 0.2]

    await write_memory_card(card, writer, embed_fn)

    writer.upsert.assert_awaited_once()
    kwargs = writer.upsert.await_args.kwargs
    assert kwargs["point_id"] == "s1:q1"
    assert kwargs["payload"]["dimension_scores"] == {"thinking": 0.6}


@pytest.mark.asyncio
async def test_grade_and_remember_skips_write_when_untrusted():
    writer = AsyncMock()
    result = await grade_and_remember(
        make_grade(JudgeVerdict.FAIL), make_rubric(), 4, ("ds",), writer, lambda t: [0.0],
    )
    assert result is None
    writer.upsert.assert_not_awaited()