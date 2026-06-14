"""Tests for language allow-list and session completion."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.features.code.constants import SupportedLanguage, validate_language
from app.features.code.models import (
    CodeAssessmentSession,
    CodeChallenge,
    CodeChallengeAttempt,
    SessionStatus,
)
from app.features.code.schemas import ChallengeCreate, TestCaseCreate
from app.features.code import service
from app.features.code.timers import utcnow


def test_validate_language_rejects_unknown():
    with pytest.raises(ValueError, match="Unsupported language"):
        validate_language("haskell")


def test_validate_language_accepts_javascript():
    assert validate_language("javascript") == SupportedLanguage.JAVASCRIPT


def test_challenge_create_rejects_invalid_language():
    with pytest.raises(ValidationError):
        ChallengeCreate(
            title="T",
            description="D",
            starter_code="pass",
            language="haskell",  # type: ignore[arg-type]
            test_cases=[
                TestCaseCreate(input='print(solution())', expected_output=""),
            ],
        )


def test_challenge_create_accepts_javascript():
    payload = ChallengeCreate(
        title="T",
        description="D",
        starter_code="function solution() {}\nmodule.exports = { solution };",
        language=SupportedLanguage.JAVASCRIPT,
        test_cases=[
            TestCaseCreate(input='console.log(solution())', expected_output="ok"),
        ],
    )
    assert payload.language == SupportedLanguage.JAVASCRIPT


def test_challenge_create_accepts_python_enum():
    payload = ChallengeCreate(
        title="T",
        description="D",
        starter_code="def solution(): pass",
        language=SupportedLanguage.PYTHON,
        test_cases=[TestCaseCreate(input='print(solution())', expected_output="ok")],
    )
    assert payload.language == SupportedLanguage.PYTHON


@pytest.mark.integration
class TestSessionCompletion:
    @pytest.mark.asyncio
    async def test_complete_session_requires_confirmation_for_unsubmitted(self, db_session):
        challenge = CodeChallenge(
            title="C",
            description="D",
            starter_code="def solution(): pass",
            language="python",
            time_limit_seconds=20,
            candidate_time_seconds=600,
        )
        db_session.add(challenge)
        await db_session.flush()

        assessment = CodeAssessmentSession(
            session_id="assess-complete-test",
            profile_json="{}",
            config_snapshot='{"challenges":[]}',
            status=SessionStatus.ACTIVE,
            started_at=utcnow(),
            expires_at=utcnow() + timedelta(hours=1),
        )
        db_session.add(assessment)
        await db_session.flush()
        db_session.add(
            CodeChallengeAttempt(
                assessment_session_id=assessment.id or 0,
                challenge_id=challenge.id or 0,
                started_at=utcnow(),
                expires_at=utcnow() + timedelta(minutes=30),
            )
        )
        await db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await service.complete_assessment_session(
                db_session,
                "assess-complete-test",
                confirm_unsubmitted=False,
            )
        assert exc_info.value.status_code == 409

        summary = await service.complete_assessment_session(
            db_session,
            "assess-complete-test",
            confirm_unsubmitted=True,
        )
        assert summary.status == "completed"
        assert summary.challenges_submitted == 0
        assert summary.challenges_total == 1
