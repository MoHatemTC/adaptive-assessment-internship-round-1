"""Tests for distinct multi-challenge fallback templates."""

from __future__ import annotations

from app.challenges.fallback_templates import fallback_challenge_at_index
from app.challenges.generator import _fallback_challenges
from app.challenges.schemas import PlatformChallengeConfig, UserProfile
from app.features.code.constants import SupportedLanguage


def test_fallback_templates_are_distinct_per_index():
    profile = UserProfile(name="Alex", skills=["Python"], experience_level="beginner")
    config = PlatformChallengeConfig()
    first = fallback_challenge_at_index(0, SupportedLanguage.PYTHON, profile, config)
    second = fallback_challenge_at_index(1, SupportedLanguage.PYTHON, profile, config)
    assert first.title != second.title
    assert first.category != second.category


def test_fallback_challenges_respects_admin_count():
    profile = UserProfile(name="Alex", skills=["Python"], experience_level="beginner")
    config = PlatformChallengeConfig()
    config.challenge.challenges_per_candidate = 3
    result = _fallback_challenges(profile, config)
    assert len(result.challenges) == 3
    titles = {challenge.title for challenge in result.challenges}
    assert len(titles) == 3
