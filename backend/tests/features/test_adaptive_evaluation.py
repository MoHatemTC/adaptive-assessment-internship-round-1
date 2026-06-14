"""Tests for adaptive memory card evaluation."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.evaluation.schemas import DimensionScores, EvaluationResult, ScoreBreakdown
from app.features.code.adaptive_schemas import CodeToolInput
from app.features.code.evaluation_memory import evaluate_turn_and_persist_card, run_adaptive_code_turn_from_input
from app.features.code.grading import GradingOutcome, dimension_signals_from_evaluation
from app.features.code.models import CodeMemoryCard
from app.features.code.schemas import ExecutionOutcome, TestCaseResult


def _mock_evaluation() -> EvaluationResult:
    return EvaluationResult(
        challenge_id=1,
        score=82,
        status="Passed",
        breakdown=ScoreBreakdown(correctness=30, completeness=12, code_quality=18),
        dimension_scores=DimensionScores(
            correctness=0.9,
            completeness=0.8,
            code_quality=0.75,
            performance=0.7,
            creativity=0.6,
            documentation=0.5,
        ),
        feedback_summary="Solid work",
    )


def _mock_grading() -> GradingOutcome:
    evaluation = _mock_evaluation()
    return GradingOutcome(
        outcome=ExecutionOutcome.SUCCESS,
        results=[
            TestCaseResult(
                test_case_id="1",
                passed=True,
                actual_output="2",
                expected_output="2",
                execution_time_ms=10.0,
            )
        ],
        sandbox_error=None,
        pass_rate=1.0,
        passed_count=1,
        total_tests=1,
        visible_results=[],
        evaluation=evaluation,
        scores=[],
        passed=True,
        normalized_score=0.82,
        metadata={"total_tests": 1, "passed_tests": 1, "hidden_tests_count": 0},
    )


@pytest.mark.asyncio
async def test_dimension_signals_from_evaluation():
    signals = dimension_signals_from_evaluation(_mock_evaluation())
    assert signals["correctness"] == 0.9
    assert len(signals) == 6


@pytest.mark.asyncio
async def test_evaluate_turn_persists_memory_card(db_session, sample_profile):
    from app.features.code import adaptive_service

    session = await adaptive_service.start_adaptive_session(db_session, sample_profile)
    challenge_id = session.challenges[0].challenge_id

    with patch(
        "app.features.code.evaluation_memory.grade_submission_in_sandbox",
        new=AsyncMock(return_value=_mock_grading()),
    ):
        output, card, *_rest = await evaluate_turn_and_persist_card(
            db_session,
            code_session_id=session.session_id,
            challenge_id=challenge_id,
            submitted_code="def solution(x): return x",
        )
        await db_session.commit()

    assert output.memory_card_id == card.id
    assert output.objective_pass_rate == 1.0
    assert card.problem_type
    assert json.loads(card.dimension_signals_json)["correctness"] == 0.9


@pytest.mark.asyncio
async def test_run_adaptive_code_turn_from_input(db_session, sample_profile):
    from app.features.code import adaptive_service
    from app.admin.service import get_platform_challenge_config

    session = await adaptive_service.start_adaptive_session(db_session, sample_profile)
    config = await get_platform_challenge_config(db_session)

    with patch(
        "app.features.code.evaluation_memory.grade_submission_in_sandbox",
        new=AsyncMock(return_value=_mock_grading()),
    ):
        tool_input = CodeToolInput(
            code_session_id=session.session_id,
            learner_profile=sample_profile,
            admin_config=config,
            target_difficulty="medium",
            challenge_id=session.challenges[0].challenge_id,
            submitted_code="def solution(x): return x",
        )
        output = await run_adaptive_code_turn_from_input(db_session, tool_input)
        await db_session.commit()

    assert isinstance(output.memory_card_id, int)
    assert output.passed is True
