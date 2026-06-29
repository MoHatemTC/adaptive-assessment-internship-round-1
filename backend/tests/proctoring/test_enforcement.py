"""Tests for server-side proctoring enforcement gates."""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi import HTTPException

from app.admin.models import Assessment
from app.core.database import async_session, engine
from app.core.security import hash_token
from app.proctoring.enforcement import assert_session_ready_for_tools
from app.proctoring.models import ProctoringEvent
from app.sessions.models import AssessmentSession


def _token_hash(suffix: str) -> str:
    return hash_token(f"enforcement-test-{suffix}")


@pytest.mark.asyncio
async def test_assert_session_ready_rejects_pending():
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    try:
        async with async_session() as db:
            db.add(
                Assessment(
                    id=assessment_id,
                    title="Enforcement",
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
                    token_hash=_token_hash(session_id),
                )
            )
            await db.commit()
            row = await db.get(AssessmentSession, session_id)
            with pytest.raises(HTTPException) as exc:
                await assert_session_ready_for_tools(db, row)
            assert exc.value.status_code == 403
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_assert_session_ready_requires_identity_when_camera_required():
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    try:
        async with async_session() as db:
            db.add(
                Assessment(
                    id=assessment_id,
                    title="Enforcement",
                    prompt="x",
                    blueprint_json="{}",
                    tool_config=json.dumps({"proctoring": {"require_camera": True}}),
                    status="active",
                )
            )
            db.add(
                AssessmentSession(
                    id=session_id,
                    assessment_id=assessment_id,
                    learner_profile_json=json.dumps({"consent_given": True}),
                    status="active",
                    token_hash=_token_hash(session_id),
                )
            )
            await db.commit()
            row = await db.get(AssessmentSession, session_id)
            with pytest.raises(HTTPException) as exc:
                await assert_session_ready_for_tools(db, row)
            assert exc.value.status_code == 403
            assert "Identity" in exc.value.detail
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_assert_session_ready_rejects_flagged():
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    try:
        async with async_session() as db:
            db.add(
                Assessment(
                    id=assessment_id,
                    title="Enforcement",
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
                    status="flagged",
                    token_hash=_token_hash(session_id),
                )
            )
            await db.commit()
            row = await db.get(AssessmentSession, session_id)
            with pytest.raises(HTTPException) as exc:
                await assert_session_ready_for_tools(db, row)
            assert exc.value.status_code == 403
            assert "flagged" in exc.value.detail.lower()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_assert_session_ready_passes_with_identity_verified():
    session_id = str(uuid.uuid4())
    assessment_id = str(uuid.uuid4())
    try:
        async with async_session() as db:
            db.add(
                Assessment(
                    id=assessment_id,
                    title="Enforcement",
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
                    status="active",
                    token_hash=_token_hash(session_id),
                )
            )
            db.add(
                ProctoringEvent(
                    session_id=session_id,
                    event_type="identity_verified",
                    severity="low",
                )
            )
            await db.commit()
            row = await db.get(AssessmentSession, session_id)
            policy = await assert_session_ready_for_tools(db, row)
            assert policy.require_camera is True
    finally:
        await engine.dispose()
