"""Tests for VLM-based camera proctoring."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.admin.models import Assessment
from app.core.database import async_session, engine
from app.proctoring import service
from app.proctoring.vlm_face import (
    CameraAnalysisResult,
    CameraViolation,
    violations_from_analysis,
)
from app.sessions.models import AssessmentSession
from app.shared.schemas.proctoring import CameraAnalyzeRequest


def test_violations_from_clean_frame():
    analysis = CameraAnalysisResult(
        face_visible=True,
        person_count=1,
        face_count=1,
        camera_obstructed=False,
        looking_at_screen=True,
        identity_match_score=0.9,
        identity_matches_reference=True,
    )
    assert violations_from_analysis(analysis, has_reference=True, match_threshold=0.7) == []


def test_violations_from_face_absent_when_person_present_but_not_visible():
    analysis = CameraAnalysisResult(
        face_visible=False,
        person_count=1,
        face_count=1,
        camera_obstructed=False,
        looking_at_screen=False,
        identity_match_score=None,
        identity_matches_reference=None,
    )
    violations = violations_from_analysis(analysis, has_reference=False, match_threshold=0.7)
    assert any(v.event_type == "face_absent" for v in violations)


def test_violations_from_multiple_persons_and_mismatch():
    analysis = CameraAnalysisResult(
        face_visible=True,
        person_count=2,
        face_count=2,
        camera_obstructed=False,
        looking_at_screen=True,
        identity_match_score=0.3,
        identity_matches_reference=False,
    )
    violations = violations_from_analysis(analysis, has_reference=True, match_threshold=0.7)
    types = {v.event_type for v in violations}
    assert "multiple_persons_detected" in types
    assert "identity_mismatch" in types


@pytest.mark.asyncio
async def test_analyze_camera_records_violations():
    session_id = ""
    try:
        async with async_session() as db:
            session_id = str(uuid.uuid4())
            assessment_id = str(uuid.uuid4())
            db.add(
                Assessment(
                    id=assessment_id,
                    title="Camera VLM",
                    prompt="x",
                    blueprint_json="{}",
                    tool_config=json.dumps(
                        {"proctoring": {"high_severity_threshold": 3}}
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

        analysis = CameraAnalysisResult(
            face_visible=False,
            person_count=0,
            face_count=0,
            camera_obstructed=True,
            looking_at_screen=False,
            identity_match_score=None,
            identity_matches_reference=None,
        )
        violations = [
            CameraViolation(
                event_type="face_absent",
                severity="high",
                description="No face visible in camera frame",
            ),
            CameraViolation(
                event_type="camera_obstructed",
                severity="high",
                description="Camera appears covered or unusable",
            ),
        ]

        with (
            patch(
                "app.proctoring.service.get_proctoring_settings"
            ) as mock_settings,
            patch(
                "app.proctoring.service.analyze_camera_frame",
                new_callable=AsyncMock,
                return_value=(analysis, violations),
            ),
        ):
            mock_settings.return_value.vlm_configured = True
            mock_settings.return_value.FACE_MATCH_THRESHOLD = 0.7

            async with async_session() as db:
                response = await service.analyze_camera(
                    db,
                    CameraAnalyzeRequest(
                        session_id=session_id,
                        frame_b64="aGVsbG8=",
                    ),
                )
                await db.commit()

        assert response.compliant is False
        assert response.face_visible is False
        assert len(response.violations) == 2
        assert len(response.events_recorded) == 2

        async with async_session() as db:
            summary = await service.get_session_integrity(db, session_id)
            assert summary.high_severity_count == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_analyze_camera_requires_consent():
    session_id = ""
    try:
        async with async_session() as db:
            session_id = str(uuid.uuid4())
            assessment_id = str(uuid.uuid4())
            db.add(
                Assessment(
                    id=assessment_id,
                    title="Camera VLM",
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
                    learner_profile_json=json.dumps({"consent_given": False}),
                    status="active",
                )
            )
            await db.commit()

        async with async_session() as db:
            with pytest.raises(HTTPException) as exc_info:
                await service.analyze_camera(
                    db,
                    CameraAnalyzeRequest(
                        session_id=session_id,
                        frame_b64="aGVsbG8=",
                    ),
                )
            assert exc_info.value.status_code == 400
    finally:
        await engine.dispose()
