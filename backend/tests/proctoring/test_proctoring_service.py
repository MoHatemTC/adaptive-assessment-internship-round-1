"""Unit and integration tests for proctoring service and API."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

import pytest
from fastapi import HTTPException
from sqlmodel import select

from app.admin.models import Assessment
from app.core.database import async_session, engine
from app.proctoring import service
from app.proctoring.identity import FaceMatchResult
from app.proctoring.models import ProctoringEvent
from app.proctoring.service import compute_verification_status
from app.sessions.models import AssessmentSession
from app.shared.schemas.proctoring import (
    IdentityVerifyRequest,
    ProctoringEventCreate,
    ProctoringPolicy,
)


@dataclass
class _MockFaceProvider:
    matched: bool = True
    score: float = 0.92

    async def compare(self, reference_b64: str, live_b64: str) -> FaceMatchResult:
        return FaceMatchResult(score=self.score, matched=self.matched)


async def _seed_session(
    db,
    *,
    threshold: int = 3,
    consent: bool = True,
    status: str = "active",
) -> tuple[str, str]:
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    db.add(
        Assessment(
            id=assessment_id,
            title="Integrity Test",
            prompt="Test proctoring.",
            blueprint_json=json.dumps({}),
            tool_config=json.dumps(
                {"proctoring": {"high_severity_threshold": threshold}}
            ),
            status="active",
        )
    )
    db.add(
        AssessmentSession(
            id=session_id,
            assessment_id=assessment_id,
            learner_profile_json=json.dumps(
                {"name": "Learner", "consent_given": consent}
            ),
            status=status,
        )
    )
    await db.flush()
    return session_id, assessment_id


def test_compute_verification_status_pending():
    status_value = compute_verification_status(
        session_status="active",
        events=[],
        policy=ProctoringPolicy(high_severity_threshold=3),
    )
    assert status_value == "pending"


def test_compute_verification_status_identity_failed():
    event = ProctoringEvent(
        session_id="s1",
        event_type="identity_fail",
        severity="high",
    )
    status_value = compute_verification_status(
        session_status="active",
        events=[event],
        policy=ProctoringPolicy(high_severity_threshold=3),
    )
    assert status_value == "identity_failed"


def test_compute_verification_status_flagged_by_count():
    events = [
        ProctoringEvent(session_id="s1", event_type="tab_switch", severity="high"),
        ProctoringEvent(session_id="s1", event_type="copy_paste", severity="high"),
    ]
    status_value = compute_verification_status(
        session_status="active",
        events=events,
        policy=ProctoringPolicy(high_severity_threshold=2),
    )
    assert status_value == "flagged"


def test_compute_verification_status_verified():
    events = [
        ProctoringEvent(
            session_id="s1",
            event_type="identity_verified",
            severity="low",
        ),
        ProctoringEvent(session_id="s1", event_type="tab_switch", severity="low"),
    ]
    status_value = compute_verification_status(
        session_status="active",
        events=events,
        policy=ProctoringPolicy(high_severity_threshold=3),
    )
    assert status_value == "verified"


@pytest.mark.asyncio
async def test_record_event_persists_and_flags_at_threshold():
    session_id, _ = "", ""
    try:
        async with async_session() as db:
            session_id, _ = await _seed_session(db, threshold=2)
            await db.commit()

        async with async_session() as db:
            await service.record_event(
                db,
                ProctoringEventCreate(
                    session_id=session_id,
                    event_type="tab_switch",
                    severity="high",
                ),
            )
            await db.commit()

        async with async_session() as db:
            session = await db.get(AssessmentSession, session_id)
            assert session is not None
            assert session.status == "active"

            await service.record_event(
                db,
                ProctoringEventCreate(
                    session_id=session_id,
                    event_type="copy_paste",
                    severity="high",
                ),
            )
            await db.commit()

        async with async_session() as db:
            session = await db.get(AssessmentSession, session_id)
            assert session is not None
            assert session.status == "flagged"

            result = await db.exec(
                select(ProctoringEvent).where(
                    ProctoringEvent.session_id == session_id
                )
            )
            assert len(result.all()) == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_verify_identity_success():
    session_id = ""
    try:
        async with async_session() as db:
            session_id, _ = await _seed_session(db)
            await db.commit()

        async with async_session() as db:
            response = await service.verify_identity(
                db,
                IdentityVerifyRequest(
                    session_id=session_id,
                    reference_image_b64="aGVsbG8=",
                    live_capture_b64="aGVsbG8=",
                ),
                _MockFaceProvider(matched=True, score=0.95),
            )
            await db.commit()

        assert response.verified is True
        assert response.verification_status == "verified"
        assert response.match_score == 0.95

        async with async_session() as db:
            summary = await service.get_session_integrity(db, session_id)
            assert summary.identity_verified is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_verify_identity_failure():
    session_id = ""
    try:
        async with async_session() as db:
            session_id, _ = await _seed_session(db)
            await db.commit()

        async with async_session() as db:
            response = await service.verify_identity(
                db,
                IdentityVerifyRequest(
                    session_id=session_id,
                    reference_image_b64="aGVsbG8=",
                    live_capture_b64="d29ybGQ=",
                ),
                _MockFaceProvider(matched=False, score=0.2),
            )
            await db.commit()

        assert response.verified is False
        assert response.verification_status == "identity_failed"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_verify_identity_requires_consent():
    session_id = ""
    try:
        async with async_session() as db:
            session_id, _ = await _seed_session(db, consent=False)
            await db.commit()

        async with async_session() as db:
            with pytest.raises(HTTPException) as exc_info:
                await service.verify_identity(
                    db,
                    IdentityVerifyRequest(
                        session_id=session_id,
                        reference_image_b64="aGVsbG8=",
                        live_capture_b64="aGVsbG8=",
                    ),
                    _MockFaceProvider(),
                )
            assert exc_info.value.status_code == 400
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_session_integrity_summary():
    session_id = ""
    try:
        async with async_session() as db:
            session_id, _ = await _seed_session(db, threshold=5)
            await db.commit()

        async with async_session() as db:
            await service.record_event(
                db,
                ProctoringEventCreate(
                    session_id=session_id,
                    event_type="screenshot",
                    severity="medium",
                ),
            )
            await db.commit()

        async with async_session() as db:
            summary = await service.get_session_integrity(db, session_id)
            assert summary.session_id == session_id
            assert summary.verification_status == "pending"
            assert summary.high_severity_count == 0
            assert summary.threshold == 5
            assert len(summary.events) == 1
    finally:
        await engine.dispose()
