"""Async tests for session radar report assembly."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.admin.models import Assessment
from app.core.database import async_session
from app.core.security import generate_session_token, hash_token
from app.reports.service import build_session_radar_report
from app.sessions.models import AssessmentSession, MemoryCard, SkillDimensionScore


@pytest.mark.asyncio
async def test_build_session_radar_report_aggregates_scores_and_memory():
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())

    async with async_session() as db:
        db.add(
            Assessment(
                id=assessment_id,
                title="Report Test",
                prompt="x",
                blueprint_json="{}",
                tool_config="{}",
                status="active",
            )
        )
        db.add(
            AssessmentSession(
                id=session_id,
                assessment_id=assessment_id,
                learner_profile_json=json.dumps({"name": "Learner"}),
                status="completed",
                token_hash=hash_token(generate_session_token()),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                completed_at=datetime.now(timezone.utc),
            )
        )
        db.add(
            SkillDimensionScore(
                session_id=session_id,
                question_index=0,
                tool_type="voice",
                thinking=8,
                soft=6,
                work=None,
                digital_ai=7,
                growth=5,
            )
        )
        db.add(
            MemoryCard(
                session_id=session_id,
                tool_type="voice",
                question_index=0,
                difficulty="intermediate",
                evidence_summary="Explained trade-offs clearly.",
                dimension_signals=json.dumps(
                    {
                        "thinking": True,
                        "soft": True,
                        "work": False,
                        "digital_ai": False,
                        "growth": False,
                    }
                ),
                passed=True,
            )
        )
        await db.flush()

        report = await build_session_radar_report(db, session_id)

    assert report.session_id == session_id
    assert report.overall_score is not None
    assert report.questions_answered == 1
    assert "voice" in report.tools_used
    assert report.evidence_highlights == ["Explained trade-offs clearly."]
    thinking = next(point for point in report.dimensions if point.name == "thinking")
    assert thinking.score == 8
    assert report.integrity is not None
    assert report.integrity.verification_status == "pending"
    assert report.integrity.identity_verified is False


@pytest.mark.asyncio
async def test_build_session_radar_report_dedupes_evidence_highlights():
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    duplicate = "Submission passed with sandbox correctness 100%."

    async with async_session() as db:
        db.add(
            Assessment(
                id=assessment_id,
                title="Report Test",
                prompt="x",
                blueprint_json="{}",
                tool_config="{}",
                status="active",
            )
        )
        db.add(
            AssessmentSession(
                id=session_id,
                assessment_id=assessment_id,
                learner_profile_json=json.dumps({"name": "Learner"}),
                status="completed",
                token_hash=hash_token(generate_session_token()),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                completed_at=datetime.now(timezone.utc),
            )
        )
        for index in range(3):
            db.add(
                MemoryCard(
                    session_id=session_id,
                    tool_type="coding",
                    question_index=index,
                    difficulty="beginner",
                    evidence_summary=duplicate,
                    dimension_signals="{}",
                    passed=True,
                )
            )
        await db.flush()

        report = await build_session_radar_report(db, session_id)

    assert report.evidence_highlights == [duplicate]
