"""Tests for adaptive analysis aggregation."""

from __future__ import annotations

import json

import pytest

from app.features.code.analysis import analyze_memory_cards
from app.features.code.models import CodeMemoryCard


def _card(
    *,
    card_id: int,
    problem_type: str,
    pass_rate: float,
    rubric: float = 0.7,
) -> CodeMemoryCard:
    return CodeMemoryCard(
        id=card_id,
        code_session_id="assess-test",
        challenge_id=card_id,
        problem_type=problem_type,
        difficulty="intermediate",
        language="python",
        pass_rate=pass_rate,
        efficiency=0.8,
        rubric_score=rubric,
        dimension_signals_json=json.dumps(
            {
                "correctness": pass_rate,
                "completeness": pass_rate,
                "code_quality": rubric,
                "performance": 0.6,
                "creativity": 0.5,
                "documentation": 0.5,
            }
        ),
        passed=pass_rate >= 0.5,
        test_results_json="[]",
    )


def test_analyze_memory_cards_strong_and_weak_types():
    cards = [
        _card(card_id=1, problem_type="arrays", pass_rate=0.9),
        _card(card_id=2, problem_type="strings", pass_rate=0.3),
    ]
    analysis = analyze_memory_cards(cards)
    assert analysis.turns_completed == 2
    assert "arrays" in analysis.strong_problem_types
    assert "strings" in analysis.weak_problem_types
    assert analysis.average_pass_rate > 0


@pytest.mark.asyncio
async def test_analyze_session_after_two_turns(db_session, sample_profile):
    from app.features.code import adaptive_service
    from app.features.code.adaptive_schemas import AdaptiveSubmitRequest
    from app.features.code.analysis import analyze_session
    from unittest.mock import AsyncMock, patch

    from tests.features.test_adaptive_evaluation import _mock_grading

    session = await adaptive_service.start_adaptive_session(db_session, sample_profile)
    challenge_id = session.challenges[0].challenge_id

    with patch(
        "app.features.code.evaluation_memory.grade_submission_in_sandbox",
        new=AsyncMock(return_value=_mock_grading()),
    ):
        await adaptive_service.submit_adaptive_turn(
            db_session,
            session.session_id,
            AdaptiveSubmitRequest(
                challenge_id=challenge_id,
                submitted_code="def solution(x): return x",
            ),
        )

    analysis = await analyze_session(db_session, session.session_id)
    assert analysis.turns_completed >= 1
