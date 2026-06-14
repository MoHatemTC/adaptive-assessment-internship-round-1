"""Integration tests for the adaptive HTTP loop."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.features.code.adaptive_schemas import AdaptiveSubmitRequest
from app.features.code import adaptive_service
from tests.features.test_adaptive_evaluation import _mock_grading


@pytest.mark.asyncio
async def test_adaptive_loop_start_submit_analysis(db_session, sample_profile):
    with patch(
        "app.features.code.evaluation_memory.grade_submission_in_sandbox",
        new=AsyncMock(return_value=_mock_grading()),
    ), patch(
        "app.challenges.generator.generate_single_adaptive_challenge",
        new=AsyncMock(side_effect=lambda profile, config, decision: __import__(
            "app.challenges.fallback_templates", fromlist=["fallback_challenge_at_index"]
        ).fallback_challenge_at_index(0, __import__(
            "app.features.code.constants", fromlist=["SupportedLanguage"]
        ).SupportedLanguage.PYTHON, profile, config)),
    ):
        session = await adaptive_service.start_adaptive_session(db_session, sample_profile)
        assert session.adaptive is True
        assert len(session.challenges) == 1

        first_id = session.challenges[0].challenge_id
        response = await adaptive_service.submit_adaptive_turn(
            db_session,
            session.session_id,
            AdaptiveSubmitRequest(
                challenge_id=first_id,
                submitted_code="def solution(x): return x",
            ),
        )
        assert response.turns_completed == 1
        assert response.message

        analysis = await adaptive_service.get_adaptive_analysis(db_session, session.session_id)
        assert analysis.turns_completed == 1

        refreshed = await adaptive_service.get_adaptive_session_view(db_session, session.session_id)
        assert len(refreshed.challenges) >= 1
