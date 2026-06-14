"""Tests for the shared LLM evaluator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.evaluation.evaluator import evaluate_code_submission, evaluation_to_rubric_scores
from app.evaluation.schemas import CodeEvaluationContext, PlatformEvaluationConfig


@pytest.fixture
def sample_context() -> CodeEvaluationContext:
    return CodeEvaluationContext(
        challenge_id=1,
        title="Reverse String",
        description="Return the reversed string.",
        submitted_code="def solution(s): return s[::-1]",
        correctness_ratio=1.0,
        performance_ratio=0.95,
        passed_tests=4,
        total_tests=4,
    )


class TestEvaluator:
    @pytest.mark.asyncio
    async def test_evaluate_returns_full_result(self, sample_context: CodeEvaluationContext):
        mock_response = MagicMock()
        mock_response.content = """{
            "dimension_scores": {
                "correctness": 1.0,
                "completeness": 0.9,
                "code_quality": 0.85,
                "performance": 0.95,
                "creativity": 0.7,
                "documentation": 0.6
            },
            "strengths": ["Clear logic"],
            "weaknesses": ["No docstring"],
            "recommendations": ["Add type hints"],
            "next_difficulty": "Intermediate",
            "feedback_summary": "Solid solution."
        }"""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        with patch(
            "app.evaluation.evaluator.get_structured_llm_with_tracing",
            return_value=(mock_llm, []),
        ):
            with patch("app.evaluation.evaluator.get_settings") as mock_settings:
                mock_settings.return_value.LITELLM_API_KEY.get_secret_value.return_value = "sk-test"
                mock_settings.return_value.LITELLM_MODEL = "gpt-4o"
                result = await evaluate_code_submission(sample_context)

        assert result.score > 0
        assert result.status in ("Passed", "Failed")
        assert result.breakdown.correctness > 0
        assert result.strengths == ["Clear logic"]
        assert result.next_difficulty == "Intermediate"
        assert result.dimension_scores.correctness == 1.0
        assert result.dimension_scores.performance == 0.95

    @pytest.mark.asyncio
    async def test_evaluate_fallback_without_api_key(self, sample_context: CodeEvaluationContext):
        with patch("app.evaluation.evaluator.get_settings") as mock_settings:
            mock_settings.return_value.LITELLM_API_KEY.get_secret_value.return_value = ""
            result = await evaluate_code_submission(sample_context)

        assert result.score >= 0
        assert "Deterministic" in result.feedback_summary

    def test_evaluation_to_rubric_scores(self, sample_context: CodeEvaluationContext):
        from app.evaluation.evaluator import _deterministic_fallback
        from app.evaluation.defaults import DEFAULT_EVALUATION_CONFIG

        result = _deterministic_fallback(sample_context, DEFAULT_EVALUATION_CONFIG)
        rubric = evaluation_to_rubric_scores(result)
        assert len(rubric) == 6
        assert rubric[0]["dimension"] == "correctness"

    def test_passing_threshold_from_config(self, sample_context: CodeEvaluationContext):
        from app.evaluation.evaluator import _deterministic_fallback
        from app.evaluation.schemas import PlatformEvaluationConfig, ScoringSettings

        config = PlatformEvaluationConfig(
            scoring=ScoringSettings(max_score=100, passing_threshold=95)
        )
        result = _deterministic_fallback(sample_context, config)
        assert result.status in ("Passed", "Failed")
