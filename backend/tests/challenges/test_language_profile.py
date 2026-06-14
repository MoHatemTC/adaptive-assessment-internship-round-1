"""Tests for profile skill → challenge language resolution."""

from __future__ import annotations

from app.challenges.language_profile import (
    assign_challenge_languages,
    map_skill_to_language,
    resolve_profile_languages,
)
from app.challenges.schemas import PlatformChallengeConfig, UserProfile
from app.features.code.constants import SupportedLanguage


def test_map_skill_to_language():
    assert map_skill_to_language("Python") == SupportedLanguage.PYTHON
    assert map_skill_to_language("JavaScript") == SupportedLanguage.JAVASCRIPT
    assert map_skill_to_language("TypeScript") == SupportedLanguage.TYPESCRIPT
    assert map_skill_to_language("Go") == SupportedLanguage.GO
    assert map_skill_to_language("unknown-skill") is None


def test_resolve_profile_languages_prefers_executable_skills():
    profile = UserProfile(
        name="Sam",
        skills=["JavaScript", "Python"],
        experience_level="intermediate",
    )
    languages = resolve_profile_languages(profile, PlatformChallengeConfig())
    assert languages == [SupportedLanguage.JAVASCRIPT, SupportedLanguage.PYTHON]


def test_resolve_profile_languages_falls_back_when_only_non_executable():
    profile = UserProfile(
        name="Sam",
        skills=["Java", "Rust"],
        experience_level="intermediate",
    )
    languages = resolve_profile_languages(profile, PlatformChallengeConfig())
    assert languages == [SupportedLanguage.PYTHON]


def test_assign_challenge_languages_round_robin():
    assignments = assign_challenge_languages(
        [SupportedLanguage.PYTHON, SupportedLanguage.JAVASCRIPT],
        3,
    )
    assert assignments == [
        SupportedLanguage.PYTHON,
        SupportedLanguage.JAVASCRIPT,
        SupportedLanguage.PYTHON,
    ]
