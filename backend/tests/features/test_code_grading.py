"""Tests for Layer 1 grading of code submissions."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlmodel import select

from app.core.database import async_session, engine
from app.features.code import grading
from app.features.code.models import CodeChallenge, CodeSubmission, SubmissionStatus
from app.sessions.models import GradeResult
from app.shared.schemas.memory import RubricDimension, RubricScores


def _llm_rubric() -> RubricScores:
    return RubricScores(
        dimensions=[
            RubricDimension(name="approach", score=0.8, feedback="Clear strategy."),
            RubricDimension(name="efficiency", score=0.6, feedback="O(n^2) but ok."),
        ],
        overall=0.7,
    )


def test_extract_json_handles_markdown_fence():
    raw = 'Here you go:\n```json\n{"overall": 0.5, "dimensions": []}\n```\nthanks'
    assert json.loads(grading._extract_json(raw)) == {
        "overall": 0.5,
        "dimensions": [],
    }


def test_extract_llm_text_skips_thinking_blocks():
    content = [
        {"type": "thinking", "thinking": "planning"},
        {"type": "thinking", "thinking": " more"},
        '```json\n{"title": "Hi", "description": "x" * 20, "starter_code": "pass", "test_cases": []}\n```',
    ]
    text = grading._extract_llm_text(content)
    assert "planning" not in text
    assert text.startswith("```json")


def test_compose_rubric_prepends_correctness_and_blends_overall():
    composed = grading._compose_rubric(1.0, _llm_rubric())
    assert composed.dimensions[0].name == "correctness"
    assert composed.dimensions[0].score == 1.0
    # 0.5 * 1.0 + 0.5 * 0.7 = 0.85
    assert composed.overall == 0.85
    assert [d.name for d in composed.dimensions] == [
        "correctness",
        "approach",
        "efficiency",
    ]


def test_normalize_llm_rubric_scales_down_five_point_scores():
    raw = RubricScores.model_construct(
        dimensions=[
            RubricDimension.model_construct(name="Approach", score=2, feedback="ok"),
            RubricDimension.model_construct(name="efficiency", score=5, feedback="great"),
        ],
        overall=3.5,
    )
    normalized = grading._normalize_llm_rubric(raw)
    assert normalized.dimensions[0].name == "approach"
    assert normalized.dimensions[0].score == 0.4
    assert normalized.dimensions[1].score == 1.0
    assert normalized.overall == 0.7


@pytest.mark.asyncio
async def test_grade_submission_writes_grade_result(monkeypatch):
    async def _fake_llm(**kwargs) -> RubricScores:
        return _llm_rubric()

    monkeypatch.setattr(grading, "_grade_with_llm", _fake_llm)

    session_id = str(uuid.uuid4())

    # No commit: the session rolls back on exit so the shared dev DB stays
    # clean. grade_submission only flushes, so rows are visible within the txn.
    try:
        await _run_grade_assertions(session_id)
    finally:
        # Mirror the MCQ tests: dispose the pool so asyncpg connections are not
        # reused across pytest event loops.
        await engine.dispose()


async def _run_grade_assertions(session_id: str) -> None:
    async with async_session() as db:
        challenge = CodeChallenge(
            title="Reverse String",
            description="Return the reverse of the input.",
            starter_code="def solution(s): ...",
            language="python",
            time_limit_seconds=20,
        )
        db.add(challenge)
        await db.flush()

        submission = CodeSubmission(
            challenge_id=challenge.id or 0,
            session_id=session_id,
            submitted_code="def solution(s): return s[::-1]",
            status=SubmissionStatus.COMPLETED,
            score=1.0,
            passed=True,
            grading_metadata=json.dumps({"passed_tests": 4, "total_tests": 4}),
        )
        db.add(submission)
        await db.flush()

        grade = await grading.grade_submission(
            db,
            submission_id=submission.id or 0,
            session_id=session_id,
            question_index=0,
        )

        assert grade.tool_type == "coding"
        assert grade.tool_session_id == submission.id
        assert grade.question_index == 0
        assert grade.llm_judge_score is None

        rubric = RubricScores.model_validate_json(grade.rubric_scores)
        assert rubric.dimensions[0].name == "correctness"
        assert rubric.overall == 0.85

        rows = (
            await db.exec(
                select(GradeResult).where(GradeResult.session_id == session_id)
            )
        ).all()
        assert len(rows) == 1

        await db.rollback()
