"""Tests for the code feature adaptive-loop orchestration and endpoint wiring."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlmodel import select

from app.admin.models import Assessment
from app.core.database import async_session, engine
from app.features.code import adaptation, grading, loop, service
from app.features.code.models import CodeChallenge, CodeSubmission, SubmissionStatus
from app.proctoring.models import ProctoringEvent
from app.sessions.models import (
    AssessmentSession,
    GradeResult,
    MemoryCard,
    SkillDimensionScore,
)
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
    assessment_id = str(uuid.uuid4())
    try:
        async with async_session() as db:
            db.add(
                Assessment(
                    id=assessment_id,
                    title="Coding",
                    prompt="Assess coding ability.",
                    blueprint_json=json.dumps(
                        {
                            "coding": {
                                "max_questions": 5,
                                "difficulty_thresholds": {
                                    "intermediate": 5,
                                    "advanced": 8,
                                },
                            }
                        }
                    ),
                    tool_config=json.dumps({"coding": True}),
                    status="active",
                )
            )
            db.add(
                AssessmentSession(
                    id=session_id,
                    assessment_id=assessment_id,
                    learner_profile_json=json.dumps({"level": "junior"}),
                    status="active",
                )
            )
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

            contract, llm_rubric = await loop.run_adaptive_loop(
                db,
                submission_id=submission.id or 0,
                session_id=session_id,
                assessment_id=assessment_id,
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


@pytest.mark.asyncio
async def test_adaptive_submit_async_schedules_llm_upgrade(monkeypatch):
    scheduled: list[dict] = []

    def _capture_schedule(**kwargs):
        scheduled.append(kwargs)

    async def _fast_sandbox(db, payload):
        from app.features.code.schemas import SubmissionCreate

        submission = CodeSubmission(
            challenge_id=payload.challenge_id,
            session_id=payload.session_id,
            submitted_code=payload.submitted_code,
            status=SubmissionStatus.COMPLETED,
            score=1.0,
            passed=True,
            grading_metadata=json.dumps({"passed_tests": 2, "total_tests": 2}),
        )
        db.add(submission)
        await db.flush()
        from app.features.code.service import _submission_to_read

        return _submission_to_read(
            submission,
            scores=[],
            test_results=[],
            total_tests=2,
            passed_tests=2,
        )

    async def _fail_llm(**kwargs):
        raise AssertionError("adaptive submit should not block on LLM grading")

    monkeypatch.setattr(
        "app.features.code.background_grading.async_grading_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.features.code.background_grading.schedule_llm_grade_upgrade",
        _capture_schedule,
    )
    monkeypatch.setattr(service, "submit_code", _fast_sandbox)
    monkeypatch.setattr(grading, "_grade_with_llm", _fail_llm)

    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    try:
        async with async_session() as db:
            db.add(
                Assessment(
                    id=assessment_id,
                    title="Coding",
                    prompt="Assess coding ability.",
                    blueprint_json=json.dumps({"coding": {"max_questions": 5}}),
                    tool_config=json.dumps({"coding": True}),
                    status="active",
                )
            )
            db.add(
                AssessmentSession(
                    id=session_id,
                    assessment_id=assessment_id,
                    learner_profile_json=json.dumps(
                        {"level": "junior", "consent_given": True}
                    ),
                    status="active",
                )
            )
            db.add(
                ProctoringEvent(
                    session_id=session_id,
                    event_type="identity_verified",
                    severity="low",
                )
            )
            challenge = CodeChallenge(
                title="Reverse String",
                description="Return the reverse of the input.",
                starter_code="def solution(s): ...",
                language="python",
                time_limit_seconds=20,
            )
            db.add(challenge)
            await db.flush()

            response = await service.adaptive_submit(
                db,
                service.AdaptiveSubmitRequest(
                    challenge_id=challenge.id or 0,
                    session_id=session_id,
                    assessment_id=assessment_id,
                    submitted_code="def solution(s): return s[::-1]",
                    question_index=0,
                    difficulty="beginner",
                ),
            )

            assert response.contract.question_index == 1
            assert len(scheduled) == 1
            assert scheduled[0]["session_id"] == session_id
            await db.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_adaptive_submit_is_idempotent_for_identical_retry(monkeypatch):
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())

    async def _fail_submit(*args, **kwargs):
        raise AssertionError("duplicate adaptive submit should not resubmit code")

    monkeypatch.setattr(service, "submit_code", _fail_submit)
    try:
        async with async_session() as db:
            db.add(
                Assessment(
                    id=assessment_id,
                    title="Coding",
                    prompt="Assess coding ability.",
                    blueprint_json=json.dumps(
                        {
                            "coding": {
                                "max_questions": 4,
                                "difficulty_thresholds": {
                                    "intermediate": 4,
                                    "advanced": 8,
                                },
                            }
                        }
                    ),
                    tool_config=json.dumps({"coding": True}),
                    status="active",
                )
            )
            db.add(
                AssessmentSession(
                    id=session_id,
                    assessment_id=assessment_id,
                    learner_profile_json=json.dumps(
                        {"level": "junior", "consent_given": True}
                    ),
                    status="active",
                )
            )
            db.add(
                ProctoringEvent(
                    session_id=session_id,
                    event_type="identity_verified",
                    severity="low",
                )
            )
            challenge = CodeChallenge(
                title="Reverse String",
                description="Return the reverse of the input.",
                starter_code="def solution(s): ...",
                language="python",
                time_limit_seconds=20,
            )
            db.add(challenge)
            await db.flush()

            submitted_code = "def solution(s): return s[::-1]"
            submission = CodeSubmission(
                challenge_id=challenge.id or 0,
                session_id=session_id,
                submitted_code=submitted_code,
                status=SubmissionStatus.COMPLETED,
                score=1.0,
                passed=True,
                grading_metadata=json.dumps({"passed_tests": 1, "total_tests": 1}),
            )
            db.add(submission)
            await db.flush()
            db.add(
                GradeResult(
                    session_id=session_id,
                    tool_type="coding",
                    tool_session_id=submission.id or 0,
                    question_index=0,
                    rubric_scores=_llm_rubric().model_dump_json(),
                    llm_judge_score=None,
                )
            )
            db.add(
                SkillDimensionScore(
                    session_id=session_id,
                    question_index=0,
                    tool_type="coding",
                    thinking=8,
                    work=8,
                    digital_ai=8,
                )
            )
            await db.flush()

            response = await service.adaptive_submit(
                db,
                service.AdaptiveSubmitRequest(
                    challenge_id=challenge.id or 0,
                    session_id=session_id,
                    assessment_id=assessment_id,
                    submitted_code=submitted_code,
                    question_index=0,
                    difficulty="beginner",
                ),
            )

            assert response.submission_id == submission.id
            assert response.score is None
            assert response.llm_rubric is None
            assert response.contract.difficulty == "advanced"
            assert len(
                (
                    await db.exec(
                        select(GradeResult).where(GradeResult.session_id == session_id)
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


@pytest.mark.asyncio
async def test_adaptation_uses_learner_profile_for_initial_difficulty():
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    try:
        async with async_session() as db:
            db.add(
                Assessment(
                    id=assessment_id,
                    title="Coding",
                    prompt="Assess coding ability.",
                    blueprint_json=json.dumps({"coding": {"max_questions": 4}}),
                    tool_config=json.dumps({"coding": True}),
                    status="active",
                )
            )
            db.add(
                AssessmentSession(
                    id=session_id,
                    assessment_id=assessment_id,
                    learner_profile_json=json.dumps({"level": "senior"}),
                    status="active",
                )
            )
            await db.flush()

            contract = await adaptation.compute_adaptive_contract(
                db,
                session_id,
                assessment_id,
            )

            assert contract.question_index == 0
            assert contract.difficulty == "advanced"
            await db.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_adaptation_uses_admin_thresholds_and_max_questions():
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    try:
        async with async_session() as db:
            db.add(
                Assessment(
                    id=assessment_id,
                    title="Coding",
                    prompt="Assess coding ability.",
                    blueprint_json=json.dumps(
                        {
                            "coding": {
                                "max_questions": 2,
                                "difficulty_thresholds": {
                                    "intermediate": 4,
                                    "advanced": 9,
                                },
                            }
                        }
                    ),
                    tool_config=json.dumps({"coding": True}),
                    status="active",
                )
            )
            db.add(
                AssessmentSession(
                    id=session_id,
                    assessment_id=assessment_id,
                    learner_profile_json=json.dumps({"level": "junior"}),
                    status="active",
                )
            )
            db.add_all(
                [
                    SkillDimensionScore(
                        session_id=session_id,
                        question_index=0,
                        tool_type="coding",
                        thinking=4,
                        work=4,
                        digital_ai=4,
                    ),
                    SkillDimensionScore(
                        session_id=session_id,
                        question_index=1,
                        tool_type="coding",
                        thinking=4,
                        work=4,
                        digital_ai=4,
                    ),
                ]
            )
            await db.flush()

            contract = await adaptation.compute_adaptive_contract(
                db,
                session_id,
                assessment_id,
            )

            assert contract.difficulty == "intermediate"
            assert contract.stop is True
            assert contract.question_index == 2
            await db.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
