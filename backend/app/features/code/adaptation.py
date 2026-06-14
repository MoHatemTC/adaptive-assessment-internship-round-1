"""Layer 4 — select next challenge difficulty, category, and language."""

from __future__ import annotations

import random

from app.challenges.language_profile import assign_challenge_languages, resolve_profile_languages
from app.challenges.schemas import PlatformChallengeConfig, UserProfile
from app.features.code.adaptive_schemas import AdaptationDecision, LearnerCodeAnalysis
from app.features.code.models import CodeMemoryCard

_CHALLENGE_DIFFICULTIES = ["beginner", "intermediate", "advanced"]
_BLUEPRINT_TO_CHALLENGE = {
    "easy": "beginner",
    "medium": "intermediate",
    "hard": "advanced",
}
_CHALLENGE_TO_BLUEPRINT = {value: key for key, value in _BLUEPRINT_TO_CHALLENGE.items()}


def _clamp_difficulty(current: str, delta: int, allowed: list[str]) -> str:
    ordered = [level for level in _CHALLENGE_DIFFICULTIES if level in allowed] or allowed
    if current not in ordered:
        current = ordered[len(ordered) // 2] if ordered else "intermediate"
    index = ordered.index(current)
    new_index = max(0, min(len(ordered) - 1, index + delta))
    return ordered[new_index]


def initial_adaptation_decision(
    profile: UserProfile,
    config: PlatformChallengeConfig,
) -> AdaptationDecision:
    """First challenge: medium difficulty, profile-driven category and language."""
    categories = config.challenge.categories
    category = categories[0] if categories else "arrays"
    languages = resolve_profile_languages(profile, config)
    assigned = assign_challenge_languages(languages, 1)
    language = assigned[0].value if assigned else config.challenge.default_language.value
    difficulty = "intermediate"
    if profile.experience_level.lower().startswith("begin"):
        difficulty = "beginner"
    elif profile.experience_level.lower().startswith("adv"):
        difficulty = "advanced"
    allowed = config.challenge.difficulty_levels
    if difficulty not in allowed:
        difficulty = allowed[len(allowed) // 2] if allowed else "intermediate"
    return AdaptationDecision(
        next_difficulty=difficulty,
        next_category=category,
        next_language=language,
        rationale="Initial adaptive slot from profile experience and admin categories.",
    )


def decide_next_adaptation(
    analysis: LearnerCodeAnalysis,
    profile: UserProfile,
    config: PlatformChallengeConfig,
    *,
    last_card: CodeMemoryCard | None,
    current_difficulty: str,
) -> AdaptationDecision:
    """Rule-based v1 adaptation from aggregated cards and admin bounds."""
    allowed_difficulties = config.challenge.difficulty_levels
    categories = config.challenge.categories or ["arrays"]
    languages = resolve_profile_languages(profile, config)
    language = assign_challenge_languages(languages, 1)[0].value

    difficulty = current_difficulty
    rationale_parts: list[str] = []

    if last_card is not None:
        if last_card.pass_rate >= 0.85 and last_card.rubric_score >= 0.7:
            difficulty = _clamp_difficulty(difficulty, 1, allowed_difficulties)
            rationale_parts.append("Strong last turn — increased difficulty.")
        elif last_card.pass_rate < 0.5 or last_card.rubric_score < 0.4:
            difficulty = _clamp_difficulty(difficulty, -1, allowed_difficulties)
            rationale_parts.append("Weak last turn — decreased difficulty.")

    if analysis.weak_problem_types:
        category = analysis.weak_problem_types[0]
        rationale_parts.append(f"Targeting weak area: {category}.")
    elif analysis.strong_problem_types and random.random() < 0.35:
        category = random.choice(analysis.strong_problem_types)
        rationale_parts.append(f"Confidence rotation in strong area: {category}.")
    else:
        category = categories[len(analysis.strong_problem_types) % len(categories)]
        rationale_parts.append("Rotating admin category.")

    if difficulty not in allowed_difficulties:
        difficulty = allowed_difficulties[0]

    allowed_lang_values = {lang.value for lang in config.challenge.allowed_languages}
    if language not in allowed_lang_values:
        language = config.challenge.default_language.value

    return AdaptationDecision(
        next_difficulty=difficulty,
        next_category=category,
        next_language=language,
        rationale=" ".join(rationale_parts) or "Default adaptive progression.",
    )
