"""Tests for proctoring policy, batch ingest, and audio API."""

from __future__ import annotations

import json
import uuid

import pytest

from app.core.database import async_session, engine
from app.admin.models import Assessment
from app.proctoring import service
from app.sessions.models import AssessmentSession
from app.shared.schemas.proctoring import (
    AudioAnalyzeRequest,
    ProctoringEventBatchCreate,
    ProctoringEventCreate,
)


async def _seed_session(**kwargs) -> str:
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    async with async_session() as db:
        db.add(
            Assessment(
                id=assessment_id,
                title="Policy Test",
                prompt="x",
                blueprint_json="{}",
                tool_config=json.dumps(
                    {
                        "proctoring": {
                            "high_severity_threshold": 3,
                            "enabled_checks": [
                                "tab_switch",
                                "paste",
                                "audio_absent",
                                "microphone_muted",
                            ],
                            "event_cooldown_seconds": 60,
                            "require_microphone": True,
                        }
                    }
                ),
                status="active",
            )
        )
        db.add(
            AssessmentSession(
                id=session_id,
                assessment_id=assessment_id,
                learner_profile_json=json.dumps({"consent_given": True}),
                status="active",
            )
        )
        await db.commit()
    return session_id


@pytest.mark.asyncio
async def test_get_session_policy_returns_enabled_checks():
    session_id = await _seed_session()
    try:
        async with async_session() as db:
            policy = await service.get_session_policy(db, session_id)
        assert policy.session_id == session_id
        assert "tab_switch" in policy.enabled_checks
        assert policy.default_severities["paste"] == "high"
        assert policy.require_microphone is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_record_events_batch_skips_disabled_and_cooldown():
    session_id = await _seed_session()
    try:
        async with async_session() as db:
            first = await service.record_events_batch(
                db,
                ProctoringEventBatchCreate(
                    session_id=session_id,
                    events=[
                        ProctoringEventCreate(
                            session_id=session_id,
                            event_type="tab_switch",
                        ),
                        ProctoringEventCreate(
                            session_id=session_id,
                            event_type="copy",
                        ),
                    ],
                ),
            )
            await db.commit()

        assert len(first.recorded) == 1
        assert first.recorded[0].event_type == "tab_switch"
        assert any(item["reason"] == "disabled" for item in first.skipped)

        async with async_session() as db:
            second = await service.record_events_batch(
                db,
                ProctoringEventBatchCreate(
                    session_id=session_id,
                    events=[
                        ProctoringEventCreate(
                            session_id=session_id,
                            event_type="tab_switch",
                        ),
                    ],
                ),
            )
            await db.commit()

        assert len(second.recorded) == 0
        assert any(item["reason"] == "cooldown" for item in second.skipped)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_analyze_audio_records_violation():
    session_id = await _seed_session()
    try:
        async with async_session() as db:
            response = await service.analyze_audio(
                db,
                AudioAnalyzeRequest(
                    session_id=session_id,
                    average_rms=0.0,
                    microphone_muted=True,
                    microphone_enabled=True,
                ),
            )
            await db.commit()

        assert response.compliant is False
        assert len(response.events_recorded) >= 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_record_event_uses_server_severity():
    session_id = await _seed_session()
    try:
        async with async_session() as db:
            event = await service.record_event(
                db,
                ProctoringEventCreate(
                    session_id=session_id,
                    event_type="paste",
                    severity="low",
                ),
            )
            await db.commit()
        assert event.severity == "high"
    finally:
        await engine.dispose()
