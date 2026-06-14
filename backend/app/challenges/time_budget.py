"""Normalize LLM-assigned per-challenge time budgets against admin limits."""

from __future__ import annotations

from app.challenges.schemas import (
    ChallengeGenerationResult,
    GeneratedCodeChallenge,
    PlatformChallengeConfig,
)

_DIFFICULTY_WEIGHTS = {
    "beginner": 1.0,
    "easy": 1.0,
    "intermediate": 1.4,
    "medium": 1.4,
    "advanced": 1.8,
    "hard": 1.8,
}


def _difficulty_weight(difficulty: str) -> float:
    key = difficulty.lower().strip()
    return _DIFFICULTY_WEIGHTS.get(key, 1.2)


def _clamp_seconds(value: int, config: PlatformChallengeConfig) -> int:
    lo = config.challenge.min_time_per_challenge_minutes * 60
    hi = config.challenge.max_time_per_challenge_minutes * 60
    return max(lo, min(hi, value))


def allocate_fallback_times(
    challenges: list[GeneratedCodeChallenge],
    config: PlatformChallengeConfig,
) -> list[GeneratedCodeChallenge]:
    """Assign candidate_time_seconds when the LLM omits or misallocates time."""
    if not challenges:
        return challenges
    total_budget = config.challenge.total_time_minutes * 60
    weights = [_difficulty_weight(c.difficulty) for c in challenges]
    weight_sum = sum(weights) or float(len(challenges))
    raw = [int(total_budget * w / weight_sum) for w in weights]
    adjusted: list[GeneratedCodeChallenge] = []
    for challenge, seconds in zip(challenges, raw, strict=False):
        secs = _clamp_seconds(seconds, config)
        e2b_cap = min(
            challenge.time_limit_seconds,
            config.challenge.e2b_execution_timeout_seconds,
        )
        adjusted.append(
            challenge.model_copy(
                update={
                    "candidate_time_seconds": secs,
                    "time_limit_seconds": max(5, e2b_cap),
                    "estimated_duration": f"{max(1, secs // 60)} minutes",
                }
            )
        )
    return _scale_to_budget(adjusted, config)


def _scale_to_budget(
    challenges: list[GeneratedCodeChallenge],
    config: PlatformChallengeConfig,
) -> list[GeneratedCodeChallenge]:
    total_budget = config.challenge.total_time_minutes * 60
    total_assigned = sum(c.candidate_time_seconds for c in challenges)
    if total_assigned <= total_budget or total_assigned == 0:
        return challenges
    ratio = total_budget / total_assigned
    scaled: list[GeneratedCodeChallenge] = []
    for challenge in challenges:
        secs = _clamp_seconds(int(challenge.candidate_time_seconds * ratio), config)
        scaled.append(challenge.model_copy(update={"candidate_time_seconds": secs}))
    return scaled


def normalize_challenge_times(
    result: ChallengeGenerationResult,
    config: PlatformChallengeConfig,
) -> ChallengeGenerationResult:
    """Clamp and scale LLM output to respect admin time budgets."""
    count = config.challenge.challenges_per_candidate
    challenges = result.challenges[:count]
    if not challenges:
        return result

    for idx, challenge in enumerate(challenges):
        if challenge.candidate_time_seconds <= 0:
            challenges[idx] = challenge.model_copy(
                update={"candidate_time_seconds": config.challenge.min_time_per_challenge_minutes * 60}
            )

    challenges = [
        c.model_copy(
            update={
                "candidate_time_seconds": _clamp_seconds(c.candidate_time_seconds, config),
                "time_limit_seconds": min(
                    c.time_limit_seconds,
                    config.challenge.e2b_execution_timeout_seconds,
                ),
            }
        )
        for c in challenges
    ]
    challenges = _scale_to_budget(challenges, config)
    return result.model_copy(update={"challenges": challenges})
