"""Map learner profile skills to executable challenge languages."""

from __future__ import annotations

import re

from app.challenges.schemas import PlatformChallengeConfig, UserProfile
from app.features.code.constants import SupportedLanguage
from app.features.code.languages.registry import list_executable_languages

# Skill tokens (lowercase) → platform language(s), longest match wins per skill phrase.
_SKILL_LANGUAGE_MAP: dict[str, SupportedLanguage] = {
    "python": SupportedLanguage.PYTHON,
    "py": SupportedLanguage.PYTHON,
    "django": SupportedLanguage.PYTHON,
    "flask": SupportedLanguage.PYTHON,
    "fastapi": SupportedLanguage.PYTHON,
    "javascript": SupportedLanguage.JAVASCRIPT,
    "js": SupportedLanguage.JAVASCRIPT,
    "node": SupportedLanguage.JAVASCRIPT,
    "nodejs": SupportedLanguage.JAVASCRIPT,
    "react": SupportedLanguage.JAVASCRIPT,
    "vue": SupportedLanguage.JAVASCRIPT,
    "angular": SupportedLanguage.JAVASCRIPT,
    "typescript": SupportedLanguage.TYPESCRIPT,
    "ts": SupportedLanguage.TYPESCRIPT,
    "java": SupportedLanguage.JAVA,
    "spring": SupportedLanguage.JAVA,
    "kotlin": SupportedLanguage.JAVA,
    "go": SupportedLanguage.GO,
    "golang": SupportedLanguage.GO,
    "c#": SupportedLanguage.CSHARP,
    "csharp": SupportedLanguage.CSHARP,
    ".net": SupportedLanguage.CSHARP,
    "dotnet": SupportedLanguage.CSHARP,
    "ruby": SupportedLanguage.RUBY,
    "rails": SupportedLanguage.RUBY,
    "rust": SupportedLanguage.RUST,
    "c++": SupportedLanguage.CPP,
    "cpp": SupportedLanguage.CPP,
}


def _normalize_skill_token(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.strip().lower())


def map_skill_to_language(skill: str) -> SupportedLanguage | None:
    """Resolve a single profile skill string to a supported language, if recognized."""
    token = _normalize_skill_token(skill)
    if not token:
        return None
    if token in _SKILL_LANGUAGE_MAP:
        return _SKILL_LANGUAGE_MAP[token]
    for key, language in _SKILL_LANGUAGE_MAP.items():
        if key in token.split() or token in key:
            return language
    return None


def _dedupe_preserve_order(items: list[SupportedLanguage]) -> list[SupportedLanguage]:
    seen: set[SupportedLanguage] = set()
    ordered: list[SupportedLanguage] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def resolve_profile_languages(
    profile: UserProfile,
    config: PlatformChallengeConfig,
) -> list[SupportedLanguage]:
    """Languages inferred from profile skills, intersected with admin + executable set."""
    executable = set(list_executable_languages())
    admin_allowed = set(config.challenge.allowed_languages)
    matched: list[SupportedLanguage] = []
    for skill in profile.skills:
        language = map_skill_to_language(skill)
        if language is not None:
            matched.append(language)

    matched = _dedupe_preserve_order(matched)
    filtered = [lang for lang in matched if lang in admin_allowed and lang in executable]
    if filtered:
        return filtered

    default = config.challenge.default_language
    if default in admin_allowed and default in executable:
        return [default]
    return [SupportedLanguage.PYTHON]


def assign_challenge_languages(
    profile_languages: list[SupportedLanguage],
    count: int,
) -> list[SupportedLanguage]:
    """Assign one language per challenge slot (round-robin across profile languages)."""
    if count <= 0:
        return []
    if not profile_languages:
        return [SupportedLanguage.PYTHON] * count
    if len(profile_languages) == 1:
        return profile_languages * count
    return [profile_languages[index % len(profile_languages)] for index in range(count)]


def language_labels(languages: list[SupportedLanguage]) -> str:
    return ", ".join(lang.value for lang in languages)
