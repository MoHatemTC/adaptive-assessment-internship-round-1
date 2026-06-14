"""Shared bounds and allow-lists for the code execution feature."""

from enum import Enum

# Mirror Pydantic Field constraints — enforced at DB layer via CHECK constraints.
TIME_LIMIT_SECONDS_MIN = 1
TIME_LIMIT_SECONDS_MAX = 300
CANDIDATE_TIME_SECONDS_MIN = 60
CANDIDATE_TIME_SECONDS_MAX = 7200
TEST_CASE_WEIGHT_MIN_EXCLUSIVE = 0.0
TEST_CASE_WEIGHT_MAX = 100.0


class SupportedLanguage(str, Enum):
    """Languages the platform can generate challenges for."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    GO = "go"
    CSHARP = "csharp"
    RUBY = "ruby"
    RUST = "rust"
    CPP = "cpp"


SUPPORTED_LANGUAGES: frozenset[str] = frozenset(lang.value for lang in SupportedLanguage)

# Subset with E2B runners implemented today (others are generation-only until runners land).
EXECUTABLE_LANGUAGES: frozenset[SupportedLanguage] = frozenset(
    {
        SupportedLanguage.PYTHON,
        SupportedLanguage.JAVASCRIPT,
        SupportedLanguage.TYPESCRIPT,
    }
)


def validate_language(language: str) -> SupportedLanguage:
    """Reject free-form language strings at API and service boundaries."""
    normalized = language.strip().lower()
    try:
        return SupportedLanguage(normalized)
    except ValueError as exc:
        supported = ", ".join(sorted(SUPPORTED_LANGUAGES))
        raise ValueError(f"Unsupported language '{language}'. Allowed: {supported}") from exc


def is_executable(language: SupportedLanguage) -> bool:
    return language in EXECUTABLE_LANGUAGES
