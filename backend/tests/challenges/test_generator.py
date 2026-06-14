"""Tests for LLM challenge generation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.challenges.generator import generate_code_challenges
from app.challenges.schemas import UserProfile


@pytest.fixture
def sample_profile() -> UserProfile:
    return UserProfile(
        name="Alex",
        skills=["Python", "SQL"],
        experience_level="intermediate",
        interests=["algorithms"],
        career_goals=["backend engineer"],
        preferred_domains=["Programming"],
        learning_objectives=["master string manipulation"],
    )


class TestChallengeGenerator:
    @pytest.mark.asyncio
    async def test_generate_parses_llm_response(self, sample_profile: UserProfile):
        mock_response = MagicMock()
        mock_response.content = """{
            "challenges": [{
                "title": "Sum Two Numbers",
                "difficulty": "beginner",
                "category": "math",
                "description": "Return the sum of two integers.",
                "requirements": ["Implement solution(a, b)"],
                "evaluation_criteria": ["correctness"],
                "max_score": 100,
                "estimated_duration": "15 minutes",
                "starter_code": "def solution(a, b):\\n    pass",
                "language": "python",
                "time_limit_seconds": 20,
                "test_cases": [
                    {"input": "print(solution(2, 3))", "expected_output": "5", "is_hidden": false}
                ]
            }],
            "generation_notes": "Matched beginner Python skills."
        }"""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        with patch(
            "app.challenges.generator.get_structured_llm_with_tracing",
            return_value=(mock_llm, []),
        ):
            with patch("app.challenges.generator.get_settings") as mock_settings:
                mock_settings.return_value.LITELLM_API_KEY.get_secret_value.return_value = "sk-test"
                mock_settings.return_value.LITELLM_MODEL = "gpt-4o"
                result = await generate_code_challenges(sample_profile)

        assert len(result.challenges) == 1
        assert result.challenges[0].title == "Sum Two Numbers"
        assert result.challenges[0].test_cases[0].expected_output == "5"
        assert "beginner" in result.generation_notes or result.generation_notes

    @pytest.mark.asyncio
    async def test_generate_fallback_without_api_key(self, sample_profile: UserProfile):
        with patch("app.challenges.generator.get_settings") as mock_settings:
            mock_settings.return_value.LITELLM_API_KEY.get_secret_value.return_value = ""
            result = await generate_code_challenges(sample_profile)

        assert len(result.challenges) >= 1
        assert result.challenges[0].starter_code
        assert "Fallback" in result.generation_notes

    @pytest.mark.asyncio
    async def test_generate_fallback_uses_profile_languages(self):
        profile = UserProfile(
            name="Jamie",
            skills=["JavaScript", "Python"],
            experience_level="intermediate",
        )
        with patch("app.challenges.generator.get_settings") as mock_settings:
            mock_settings.return_value.LITELLM_API_KEY.get_secret_value.return_value = ""
            result = await generate_code_challenges(profile)

        assert result.challenges[0].language.value == "javascript"
