"""API tests for radar report auth and completion gating."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.admin.models import Assessment
from app.core.database import async_session, engine, get_db
from app.core.security import create_access_token, generate_session_token, hash_token
from app.main import app as fastapi_app
from app.sessions.models import AssessmentSession, SkillDimensionScore


async def _seed_completed_session(
    *,
    session_id: str,
    assessment_id: str,
    status: str = "completed",
    learner_token: str | None = None,
    create_assessment: bool = True,
    score_id: int | None = None,
) -> str:
    raw_token = learner_token or generate_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    async with async_session() as db:
        if create_assessment:
            db.add(
                Assessment(
                    id=assessment_id,
                    title="Radar Test",
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
                status=status,
                token_hash=hash_token(raw_token),
                expires_at=expires_at,
                completed_at=datetime.now(timezone.utc) if status == "completed" else None,
            )
        )
        db.add(
            SkillDimensionScore(
                id=score_id or abs(hash(session_id)) % 900_000 + 100_000,
                session_id=session_id,
                question_index=0,
                tool_type="voice",
                thinking=8,
                soft=6,
                work=7,
                digital_ai=7,
                growth=5,
            )
        )
        await db.commit()

    return raw_token


@pytest.fixture
async def reports_db_client(client):
    async def _override_get_db():
        async with async_session() as session:
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
async def test_radar_report_requires_auth(reports_db_client):
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    try:
        await _seed_completed_session(session_id=session_id, assessment_id=assessment_id)
        response = await reports_db_client.get(f"/api/v1/reports/sessions/{session_id}/radar")
        assert response.status_code == 401
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_radar_report_owner_allowed_when_completed(reports_db_client):
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    try:
        token = await _seed_completed_session(session_id=session_id, assessment_id=assessment_id)
        response = await reports_db_client.get(
            f"/api/v1/reports/sessions/{session_id}/radar",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["session_id"] == session_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_radar_report_admin_allowed_when_completed(reports_db_client):
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    try:
        await _seed_completed_session(session_id=session_id, assessment_id=assessment_id)
        admin_token = create_access_token({"sub": "admin", "role": "admin"})
        response = await reports_db_client.get(
            f"/api/v1/reports/sessions/{session_id}/radar",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_radar_report_other_learner_rejected(reports_db_client):
    session_id = str(uuid.uuid4())
    other_session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    try:
        await _seed_completed_session(session_id=session_id, assessment_id=assessment_id)
        other_token = await _seed_completed_session(
            session_id=other_session_id,
            assessment_id=assessment_id,
            create_assessment=False,
            score_id=abs(hash(other_session_id)) % 900_000 + 100_000,
        )
        response = await reports_db_client.get(
            f"/api/v1/reports/sessions/{session_id}/radar",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert response.status_code == 403
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_radar_report_blocks_mid_assessment(reports_db_client):
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    try:
        token = await _seed_completed_session(
            session_id=session_id,
            assessment_id=assessment_id,
            status="active",
        )
        response = await reports_db_client.get(
            f"/api/v1/reports/sessions/{session_id}/radar",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 409
    finally:
        await engine.dispose()
