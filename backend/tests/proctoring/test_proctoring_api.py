"""API smoke tests for proctoring routes."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.admin.models import Assessment
from app.core.database import async_session, engine, get_db
from app.main import app as fastapi_app
from app.proctoring.api import _face_provider
from app.proctoring.identity import FaceMatchResult
from app.sessions.models import AssessmentSession


async def _seed_assessment_session(
    *,
    session_id: str,
    assessment_id: str,
    consent: bool = True,
    tool_config: dict[str, object] | None = None,
) -> None:
    async with async_session() as db:
        db.add(
            Assessment(
                id=assessment_id,
                title="API Test",
                prompt="x",
                blueprint_json="{}",
                tool_config=json.dumps(tool_config or {}),
                status="active",
            )
        )
        db.add(
            AssessmentSession(
                id=session_id,
                assessment_id=assessment_id,
                learner_profile_json=json.dumps({"consent_given": consent}),
                status="active",
            )
        )
        await db.commit()


@pytest.fixture
async def proctoring_client(client):
    """HTTP client with real DB session for proctoring routes."""
    session_holder: dict[str, AsyncSession] = {}

    async def _override_get_db():
        async with async_session() as session:
            session_holder["session"] = session
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    yield client
    fastapi_app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_proctoring_health(proctoring_client):
    response = await proctoring_client.get("/api/v1/proctoring/health")
    assert response.status_code == 200
    assert response.json()["feature"] == "proctoring"


@pytest.mark.asyncio
async def test_record_event_via_api(proctoring_client):
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())

    try:
        await _seed_assessment_session(
            session_id=session_id,
            assessment_id=assessment_id,
            tool_config={"proctoring": {"high_severity_threshold": 3}},
        )

        response = await proctoring_client.post(
            "/api/v1/proctoring/events",
            json={
                "session_id": session_id,
                "event_type": "tab_switch",
                "severity": "medium",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["session_id"] == session_id
        assert body["event_type"] == "tab_switch"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_verify_identity_via_api(proctoring_client):
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())

    mock_provider = AsyncMock()
    mock_provider.compare.return_value = FaceMatchResult(score=0.88, matched=True)

    fastapi_app.dependency_overrides[_face_provider] = lambda: mock_provider
    try:
        async with async_session() as db:
            db.add(
                Assessment(
                    id=assessment_id,
                    title="API Identity",
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
                    learner_profile_json=json.dumps({"consent_given": True}),
                    status="pending",
                )
            )
            await db.commit()

        response = await proctoring_client.post(
            f"/api/v1/proctoring/sessions/{session_id}/verify-identity",
            json={
                "session_id": session_id,
                "reference_image_b64": "aGVsbG8=",
                "live_capture_b64": "aGVsbG8=",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["verified"] is True
        assert body["verification_status"] == "verified"

        integrity = await proctoring_client.get(
            f"/api/v1/proctoring/sessions/{session_id}/integrity"
        )
        assert integrity.status_code == 200
        assert integrity.json()["identity_verified"] is True
    finally:
        fastapi_app.dependency_overrides.pop(_face_provider, None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_policy_via_api(proctoring_client):
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    try:
        await _seed_assessment_session(
            session_id=session_id,
            assessment_id=assessment_id,
            tool_config={
                "proctoring": {
                    "enabled_checks": ["tab_switch", "paste", "audio_absent"],
                    "event_cooldown_seconds": 15,
                    "camera_poll_interval_seconds": 25,
                }
            },
        )
        response = await proctoring_client.get(
            f"/api/v1/proctoring/sessions/{session_id}/policy"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["session_id"] == session_id
        assert "tab_switch" in body["enabled_checks"]
        assert body["event_cooldown_seconds"] == 15
        assert body["camera_poll_interval_seconds"] == 25
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_record_events_batch_via_api(proctoring_client):
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    try:
        await _seed_assessment_session(
            session_id=session_id,
            assessment_id=assessment_id,
            tool_config={"proctoring": {"enabled_checks": ["tab_switch", "paste"]}},
        )
        response = await proctoring_client.post(
            "/api/v1/proctoring/events/batch",
            json={
                "session_id": session_id,
                "events": [
                    {"session_id": session_id, "event_type": "tab_switch"},
                    {"session_id": session_id, "event_type": "copy"},
                ],
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert len(body["recorded"]) == 1
        assert body["recorded"][0]["event_type"] == "tab_switch"
        assert any(item["reason"] == "disabled" for item in body["skipped"])
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_analyze_audio_via_api(proctoring_client):
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    try:
        await _seed_assessment_session(
            session_id=session_id,
            assessment_id=assessment_id,
            tool_config={
                "proctoring": {
                    "enabled_checks": ["audio_absent", "microphone_muted"],
                    "require_microphone": True,
                }
            },
        )
        response = await proctoring_client.post(
            f"/api/v1/proctoring/sessions/{session_id}/analyze-audio",
            json={
                "session_id": session_id,
                "average_rms": 0.0,
                "microphone_muted": True,
                "microphone_enabled": True,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["compliant"] is False
        assert len(body["violations"]) >= 1
    finally:
        await engine.dispose()
