"""Session lifecycle integration with platform-wide proctoring."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlmodel import select

from app.admin.models import Assessment
from app.core.database import async_session, engine
from app.proctoring.models import ProctoringEvent
from app.proctoring import service as proctoring_service
from app.sessions.models import AssessmentSession


@pytest.mark.asyncio
async def test_start_proctoring_session_records_session_started():
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    try:
        async with async_session() as db:
            db.add(
                Assessment(
                    id=assessment_id,
                    title="Lifecycle",
                    prompt="x",
                    blueprint_json="{}",
                    tool_config=json.dumps({"coding": True}),
                    status="active",
                )
            )
            db.add(
                AssessmentSession(
                    id=session_id,
                    assessment_id=assessment_id,
                    learner_profile_json=json.dumps({"consent_given": True}),
                    status="pending",
                )
            )
            await db.commit()

        async with async_session() as db:
            policy = await proctoring_service.start_proctoring_session(
                db,
                session_id,
                assessment_type="coding",
            )
            await db.commit()

        assert policy.session_id == session_id
        assert policy.require_camera is True

        async with async_session() as db:
            row = await db.get(AssessmentSession, session_id)
            assert row is not None
            assert row.proctoring_status == "active"
            events = (
                await db.exec(
                    select(ProctoringEvent).where(
                        ProctoringEvent.session_id == session_id,
                        ProctoringEvent.event_type == "session_started",
                    )
                )
            ).all()
            assert len(events) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_stop_proctoring_session_records_session_stopped():
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    try:
        async with async_session() as db:
            db.add(
                Assessment(
                    id=assessment_id,
                    title="Lifecycle",
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
                    learner_profile_json="{}",
                    status="active",
                    proctoring_status="active",
                )
            )
            await db.commit()

        async with async_session() as db:
            await proctoring_service.stop_proctoring_session(db, session_id)
            await db.commit()

        async with async_session() as db:
            row = await db.get(AssessmentSession, session_id)
            assert row is not None
            assert row.proctoring_status == "stopped"
            events = (
                await db.exec(
                    select(ProctoringEvent).where(
                        ProctoringEvent.session_id == session_id,
                        ProctoringEvent.event_type == "session_stopped",
                    )
                )
            ).all()
            assert len(events) == 1
    finally:
        await engine.dispose()
