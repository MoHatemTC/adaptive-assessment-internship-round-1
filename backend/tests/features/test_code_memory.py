"""Tests for Layer 2 memory card extraction of code submissions."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlmodel import select

from app.core.database import async_session, engine
from app.features.code import evaluation
from app.features.code.models import (
    CodeChallenge,
    CodeMemoryCard,
    CodeSubmission,
    SubmissionStatus,
)
from app.sessions.models import GradeResult, MemoryCard
from app.shared.schemas.memory import DimensionSignals, RubricScores


def _rubric_json() -> str:
    return RubricScores.model_validate(
        {
            "dimensions": [
                {"name": "correctness", "score": 1.0, "feedback": "All tests pass."},
                {"name": "approach", "score": 0.8, "feedback": "Clear slice."},
                {"name": "efficiency", "score": 0.7, "feedback": "Linear time."},
            ],
            "overall": 0.85,
        }
    ).model_dump_json()


@pytest.mark.asyncio
async def test_extract_memory_card_writes_both_tables(monkeypatch):
    session_id = str(uuid.uuid4())
    try:
        await _run(session_id)
    finally:
        await engine.dispose()


async def _run(session_id: str) -> None:
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
            grading_metadata=json.dumps(
                {
                    "passed_tests": 4,
                    "total_tests": 4,
                    "all_test_results": [
                        {
                            "test_case_id": "1",
                            "passed": True,
                            "actual_output": "olleh",
                            "expected_output": "olleh",
                            "execution_time_ms": 1.0,
                            "error": None,
                        }
                    ],
                }
            ),
        )
        db.add(submission)
        await db.flush()

        grade = GradeResult(
            session_id=session_id,
            tool_type="coding",
            tool_session_id=submission.id or 0,
            question_index=0,
            rubric_scores=_rubric_json(),
            llm_judge_score=None,
        )
        db.add(grade)
        await db.flush()

        card = await evaluation.extract_memory_card(
            db,
            session_id=session_id,
            question_index=0,
            grade_result_id=grade.id,
            difficulty="intermediate",
        )

        assert card.tool_type == "coding"
        assert card.difficulty == "intermediate"
        assert card.passed is True
        assert card.dimension_signals == DimensionSignals(
            thinking=True, soft=False, work=True, digital_ai=True, growth=False
        )

        memory_rows = (
            await db.exec(
                select(MemoryCard).where(MemoryCard.session_id == session_id)
            )
        ).all()
        assert len(memory_rows) == 1

        detail_rows = (
            await db.exec(
                select(CodeMemoryCard).where(CodeMemoryCard.session_id == session_id)
            )
        ).all()
        assert len(detail_rows) == 1
        detail = detail_rows[0]
        assert detail.memory_card_id == memory_rows[0].id
        assert detail.submission_id == submission.id
        assert detail.sandbox_score == 1.0
        assert detail.overall_rubric_score == 0.85
        assert json.loads(detail.test_results)[0]["test_case_id"] == "1"
        assert detail.approach_feedback == "Clear slice."
        assert detail.efficiency_feedback == "Linear time."

        await db.rollback()
