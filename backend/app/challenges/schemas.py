"""Schemas for LLM-driven challenge generation."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.features.code.constants import SupportedLanguage, validate_language


class UserProfile(BaseModel):
    """Learner profile submitted before challenge generation (Step 1)."""

    name: str = Field(min_length=1, max_length=128)
    skills: list[str] = Field(min_length=1)
    experience_level: str = Field(
        description="beginner | intermediate | advanced",
        min_length=1,
    )
    interests: list[str] = Field(default_factory=list)
    career_goals: list[str] = Field(default_factory=list)
    preferred_domains: list[str] = Field(default_factory=lambda: ["Programming"])
    previous_experience: str = ""
    learning_objectives: list[str] = Field(default_factory=list)
    prior_performance_summary: str | None = Field(
        default=None,
        description="Optional prior evaluation summary for adaptive difficulty",
    )


class ChallengeGenerationSettings(BaseModel):
    """Admin-configurable challenge generation rules."""

    categories: list[str] = Field(
        default_factory=lambda: ["algorithms", "data_structures", "strings", "arrays"]
    )
    difficulty_levels: list[str] = Field(
        default_factory=lambda: ["beginner", "intermediate", "advanced"]
    )
    challenges_per_candidate: int = Field(default=2, ge=1, le=10)
    total_time_minutes: int = Field(default=90, ge=10, le=480)
    min_time_per_challenge_minutes: int = Field(default=10, ge=5, le=120)
    max_time_per_challenge_minutes: int = Field(default=45, ge=5, le=180)
    duration_minutes: int = Field(
        default=20,
        ge=5,
        le=120,
        description="Legacy hint for LLM; prefer total_time_minutes budget",
    )
    min_complexity: int = Field(default=1, ge=1, le=10)
    max_complexity: int = Field(default=5, ge=1, le=10)
    default_language: SupportedLanguage = SupportedLanguage.PYTHON
    allowed_languages: list[SupportedLanguage] = Field(
        default_factory=lambda: list(SupportedLanguage),
        description="Languages the generator may assign to challenges",
    )
    domain: str = "Programming"

    @field_validator("default_language", "allowed_languages", mode="before")
    @classmethod
    def _coerce_language_fields(cls, value: object) -> object:
        if isinstance(value, list):
            return [
                item if isinstance(item, SupportedLanguage) else validate_language(str(item))
                for item in value
            ]
        if isinstance(value, SupportedLanguage):
            return value
        return validate_language(str(value))
    e2b_execution_timeout_seconds: int = Field(default=30, ge=5, le=120)
    e2b_template: str = Field(default="code-interpreter-v1")

    @property
    def challenges_per_request(self) -> int:
        """Backward-compatible alias used by generator call sites."""
        return self.challenges_per_candidate


class PlatformChallengeConfig(BaseModel):
    """Admin platform config consumed by the challenge generator."""

    challenge: ChallengeGenerationSettings = Field(default_factory=ChallengeGenerationSettings)


class GeneratedTestCase(BaseModel):
    """Test case produced by the LLM for E2B execution."""

    input: str
    expected_output: str
    is_hidden: bool = False
    weight: float = Field(default=1.0, gt=0)


class GeneratedCodeChallenge(BaseModel):
    """Single challenge produced by the LLM (platform + executable fields)."""

    title: str
    difficulty: str
    category: str
    description: str
    requirements: list[str] = Field(default_factory=list)
    evaluation_criteria: list[str] = Field(default_factory=list)
    max_score: int = Field(default=100, ge=1)
    estimated_duration: str = "20 minutes"
    candidate_time_seconds: int = Field(default=1200, ge=60, le=7200)
    starter_code: str
    language: SupportedLanguage = SupportedLanguage.PYTHON
    time_limit_seconds: int = Field(default=30, ge=1, le=300)

    @field_validator("language", mode="before")
    @classmethod
    def _coerce_language(cls, value: object) -> SupportedLanguage:
        if isinstance(value, SupportedLanguage):
            return value
        return validate_language(str(value))
    test_cases: list[GeneratedTestCase] = Field(min_length=1)


class ChallengeGenerationResult(BaseModel):
    """Raw LLM generation output before persistence."""

    challenges: list[GeneratedCodeChallenge] = Field(min_length=1)
    generation_notes: str = ""
