"""Tests for session judge stub and email task helpers."""

from __future__ import annotations

import json
import uuid

import pytest

from app.agent.nodes.judge import run_session_judge
from app.core.database import async_session, engine
from app.sessions.models import GradeResult


@pytest.mark.asyncio
async def test_run_session_judge_averages_rubric_overall(monkeypatch):
    def _raise_llm_unavailable(*_args, **_kwargs):
        raise RuntimeError("llm unavailable in unit test")

    monkeypatch.setattr(
        "app.agent.nodes.judge.get_llm_with_tracing",
        _raise_llm_unavailable,
    )

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
    finally:
        await engine.dispose()


def test_email_task_skips_without_smtp(monkeypatch):
    from app.workers import email_tasks

    monkeypatch.delenv("SMTP_HOST", raising=False)
    out = email_tasks.send_session_report_email("sess-1", learner_email="a@b.com")
    assert out["status"] == "skipped"
