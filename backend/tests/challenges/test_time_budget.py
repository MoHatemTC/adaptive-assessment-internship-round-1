"""Tests for per-challenge time budget normalization."""

from app.challenges.schemas import (
    ChallengeGenerationResult,
    GeneratedCodeChallenge,
    GeneratedTestCase,
    PlatformChallengeConfig,
)
from app.challenges.time_budget import normalize_challenge_times


def _challenge(seconds: int, difficulty: str = "intermediate") -> GeneratedCodeChallenge:
    return GeneratedCodeChallenge(
        title="T",
        difficulty=difficulty,
        category="strings",
        description="D",
        candidate_time_seconds=seconds,
        starter_code="def solution(): pass",
        time_limit_seconds=30,
        test_cases=[
            GeneratedTestCase(
                input="print(solution())",
                expected_output="ok",
                is_hidden=False,
            )
        ],
    )


def test_normalize_clamps_and_scales_to_total_budget():
    config = PlatformChallengeConfig()
    config.challenge.total_time_minutes = 30
    config.challenge.challenges_per_candidate = 2
    config.challenge.min_time_per_challenge_minutes = 5
    config.challenge.max_time_per_challenge_minutes = 20

    result = ChallengeGenerationResult(
        challenges=[
            _challenge(3600, "advanced"),
            _challenge(3600, "beginner"),
        ]
    )
    normalized = normalize_challenge_times(result, config)
    total = sum(c.candidate_time_seconds for c in normalized.challenges)
    assert total <= config.challenge.total_time_minutes * 60
    for challenge in normalized.challenges:
        lo = config.challenge.min_time_per_challenge_minutes * 60
        hi = config.challenge.max_time_per_challenge_minutes * 60
        assert lo <= challenge.candidate_time_seconds <= hi
