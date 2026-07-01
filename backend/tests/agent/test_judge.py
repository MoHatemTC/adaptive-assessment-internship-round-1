"""Tests for session judge and email task helpers."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from app.agent.nodes.judge import (
    SessionJudgeResult,
    approve_pending_judge_review,
    judge_result_from_json,
    judge_result_to_json,
    run_session_judge,
    store_pending_judge_review,
)
from app.core.database import async_session, engine
from app.sessions.models import AssessmentSession, GradeResult


@pytest.mark.asyncio
async def test_run_session_judge_averages_rubric_overall(monkeypatch):
    def _raise_llm_unavailable(*_args, **_kwargs):
        raise RuntimeError("llm unavailable in unit test")

    monkeypatch.setattr("app.agent.nodes.judge.get_llm_with_tracing", _raise_llm_unavailable)

    session_id = str(uuid.uuid4())
    try:
        async with async_session() as db:
            db.add(
                GradeResult(
                    session_id=session_id,
                    tool_type="coding",
                    tool_session_id=1,
                    question_index=0,
                    rubric_scores=json.dumps({"overall": 0.8, "dimensions": []}),
                )
            )
            db.add(
                GradeResult(
                    session_id=session_id,
                    tool_type="mcq",
                    tool_session_id=2,
                    question_index=1,
                    rubric_scores=json.dumps({"overall": 0.6, "dimensions": []}),
                )
            )
            await db.commit()
            result = await run_session_judge(db, session_id)
            assert result.grade_result_count == 2
            assert result.llm_judge_score == pytest.approx(0.7)
            assert result.review_status == "confirmed"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_session_judge_flags_inconsistent_grading(monkeypatch):
    async def _fake_ainvoke(_messages, config=None):
        _ = config
        return SimpleNamespace(
            content=json.dumps(
                {
                    "grading_consistent": False,
                    "review_reason": "MCQ score too high vs coding score",
                    "overall_score": 0.55,
                    "narrative": "Mixed performance.",
                }
            )
        )

    fake_llm = SimpleNamespace(ainvoke=_fake_ainvoke, temperature=0.0)
    monkeypatch.setattr(
        "app.agent.nodes.judge.get_llm_with_tracing",
        lambda *_args, **_kwargs: (fake_llm, []),
    )

    session_id = str(uuid.uuid4())
    try:
        async with async_session() as db:
            db.add(
                GradeResult(
                    session_id=session_id,
                    tool_type="mcq",
                    tool_session_id=1,
                    question_index=0,
                    rubric_scores=json.dumps({"overall": 0.95, "dimensions": []}),
                )
            )
            await db.commit()
            result = await run_session_judge(db, session_id)
            assert result.review_status == "pending_admin_review"
            assert result.review_reason == "MCQ score too high vs coding score"
            assert result.llm_judge_score == pytest.approx(0.55)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_store_and_approve_pending_judge_review():
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    try:
        async with async_session() as db:
            session = AssessmentSession(
                id=session_id,
                assessment_id=assessment_id,
                learner_profile_json=json.dumps({"name": "Ada"}),
                status="completed",
            )
            db.add(session)
            await db.commit()

            held = await run_session_judge(db, session_id)
            held = held.__class__(
                session_id=session_id,
                llm_judge_score=0.8,
                narrative="Strong overall.",
                grade_result_count=0,
                review_status="pending_admin_review",
                review_reason="manual hold",
            )
            await store_pending_judge_review(db, session, held)
            await db.commit()
            await db.refresh(session)
            assert session.status == "pending_review"
            assert session.judge_review_json is not None

            approved = await approve_pending_judge_review(db, session)
            assert approved.review_status == "confirmed"
            assert session.status == "completed"
            assert session.judge_review_json is None
    finally:
        await engine.dispose()


def test_judge_result_json_roundtrip():
    original = SessionJudgeResult(
        session_id="s1",
        llm_judge_score=0.7,
        narrative="ok",
        grade_result_count=2,
        review_status="pending_admin_review",
        review_reason="check",
    )
    result = judge_result_from_json(judge_result_to_json(original))
    assert result.session_id == "s1"
    assert result.review_status == "pending_admin_review"


def test_email_task_skips_without_smtp(monkeypatch):
    from app.workers import email_tasks

    monkeypatch.delenv("SMTP_HOST", raising=False)
    out = email_tasks.send_session_report_email(
        {"session_id": "sess-1", "status": "built"},
        learner_email="a@b.com",
    )
    assert out["status"] == "skipped"


def test_email_task_skips_when_pending_admin_review():
    from app.workers import email_tasks

    out = email_tasks.send_session_report_email(
        {
            "session_id": "sess-1",
            "status": "pending_admin_review",
            "review_reason": "inconsistent",
        },
        learner_email="a@b.com",
    )
    assert out["status"] == "skipped"
    assert out["reason"] == "pending_admin_review"
