"""Tests for the code feature adaptive-loop orchestration and endpoint wiring."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlmodel import select

from app.core.database import async_session, engine
from app.features.code import grading, service
from app.features.code.models import CodeChallenge, CodeSubmission, SubmissionStatus
from app.sessions.models import GradeResult, MemoryCard, SkillDimensionScore
from app.shared.schemas.memory import RubricDimension, RubricScores


def _llm_rubric() -> RubricScores:
    return RubricScores(
        dimensions=[
            RubricDimension(name="approach", score=0.8, feedback="Clear."),
            RubricDimension(name="efficiency", score=0.7, feedback="Linear."),
        ],
        overall=0.75,
    )


@pytest.mark.asyncio
async def test_run_adaptive_loop_persists_all_layers(monkeypatch):
    async def _fake_llm(**kwargs) -> RubricScores:
        return _llm_rubric()

    monkeypatch.setattr(grading, "_grade_with_llm", _fake_llm)
    session_id = str(uuid.uuid4())
    try:
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

            contract, llm_rubric = await service.run_adaptive_loop(
                db,
                submission_id=submission.id or 0,
                session_id=session_id,
                assessment_id="assess-1",
                question_index=0,
                difficulty="intermediate",
            )

            assert contract.session_id == session_id
            assert llm_rubric.approach_score == 0.8
            assert contract.tool_type == "coding"
            assert contract.question_index == 1
            # 1 card, passed -> score 10 -> advanced next difficulty.
            assert contract.difficulty == "advanced"

            assert len(
                (
                    await db.exec(
                        select(GradeResult).where(GradeResult.session_id == session_id)
                    )
                ).all()
            ) == 1
            assert len(
                (
                    await db.exec(
                        select(MemoryCard).where(MemoryCard.session_id == session_id)
                    )
                ).all()
            ) == 1
            assert len(
                (
                    await db.exec(
                        select(SkillDimensionScore).where(
                            SkillDimensionScore.session_id == session_id
                        )
                    )
                ).all()
            ) == 1

            await db.rollback()
    finally:
        await engine.dispose()


def test_adaptive_submit_route_registered():
    from app.main import app as fastapi_app

    paths = {getattr(route, "path", None) for route in fastapi_app.routes}
    assert "/api/v1/code/adaptive-submit" in paths
