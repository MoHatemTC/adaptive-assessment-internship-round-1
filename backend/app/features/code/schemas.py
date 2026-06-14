"""Pydantic DTOs for the code execution feature."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from app.evaluation.schemas import ScoreBreakdown
from app.challenges.schemas import UserProfile
from app.features.code.constants import (
    CANDIDATE_TIME_SECONDS_MAX,
    CANDIDATE_TIME_SECONDS_MIN,
    TEST_CASE_WEIGHT_MAX,
    TIME_LIMIT_SECONDS_MAX,
    TIME_LIMIT_SECONDS_MIN,
    SupportedLanguage,
    validate_language,
)
from app.features.code.models import SubmissionStatus

__all__ = ["UserProfile"]


class TestCaseCreate(BaseModel):
    input: str
    expected_output: str
    is_hidden: bool = False
    weight: float = Field(default=1.0, gt=0, le=TEST_CASE_WEIGHT_MAX)


class TestCaseRead(BaseModel):
    id: int
    input: str
    expected_output: str | None = None
    is_hidden: bool
    weight: float


class ChallengeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    starter_code: str
    language: SupportedLanguage = SupportedLanguage.PYTHON
    time_limit_seconds: int = Field(
        default=20,
        ge=TIME_LIMIT_SECONDS_MIN,
        le=TIME_LIMIT_SECONDS_MAX,
    )
    candidate_time_seconds: int = Field(
        default=1200,
        ge=CANDIDATE_TIME_SECONDS_MIN,
        le=CANDIDATE_TIME_SECONDS_MAX,
    )
    test_cases: list[TestCaseCreate] = Field(min_length=1)

    @field_validator("language", mode="before")
    @classmethod
    def _coerce_language(cls, value: object) -> SupportedLanguage:
        if isinstance(value, SupportedLanguage):
            return value
        return validate_language(str(value))


class ChallengeRead(BaseModel):
    id: int
    title: str
    description: str
    starter_code: str
    language: str
    time_limit_seconds: int
    candidate_time_seconds: int = 1200
    test_cases: list[TestCaseRead]
    created_at: datetime
    updated_at: datetime


class ChallengeListItem(BaseModel):
    id: int
    title: str
    language: str
    time_limit_seconds: int
    candidate_time_seconds: int = 1200
    created_at: datetime


class GeneratedChallengeRead(BaseModel):
    """Platform challenge output after LLM generation and persistence."""

    challenge_id: int
    title: str
    difficulty: str
    category: str
    description: str
    requirements: list[str]
    evaluation_criteria: list[str]
    max_score: int
    estimated_duration: str
    candidate_time_seconds: int = 1200
    starter_code: str
    language: str
    time_limit_seconds: int
    test_cases: list[TestCaseRead]


class GenerateChallengesResponse(BaseModel):
    """Response from POST /challenges/generate."""

    challenges: list[GeneratedChallengeRead]
    generation_notes: str = ""


class SubmissionCreate(BaseModel):
    challenge_id: int
    session_id: str = Field(min_length=1, max_length=64)
    submitted_code: str = Field(min_length=1)


class TestCaseResult(BaseModel):
    test_case_id: str
    passed: bool
    actual_output: str
    expected_output: str
    execution_time_ms: float
    error: str | None = None


class ExecutionOutcome(str, Enum):
    SUCCESS = "success"
    SANDBOX_ERROR = "sandbox_error"
    SANDBOX_UNAVAILABLE = "sandbox_unavailable"
    TIMEOUT = "timeout"


class SessionChallengeRead(BaseModel):
    """Challenge slot within a timed assessment session."""

    attempt_id: int
    challenge_id: int
    position: int = Field(ge=1, description="1-based index within the session")
    challenge_count: int = Field(ge=1, description="Total challenges in this session")
    title: str
    difficulty: str
    category: str
    description: str
    requirements: list[str]
    evaluation_criteria: list[str]
    max_score: int
    estimated_duration: str
    candidate_time_seconds: int
    remaining_seconds: int
    starter_code: str
    language: str
    time_limit_seconds: int
    test_cases: list[TestCaseRead]
    submitted: bool = False
    run_count: int = 0


class SessionRead(BaseModel):
    session_id: str
    status: str
    total_remaining_seconds: int
    expires_at: datetime
    challenges: list[SessionChallengeRead]
    generation_notes: str = ""
    adaptive: bool = False
    turns_completed: int = 0
    total_questions: int = 0
    current_difficulty: str = "intermediate"


class RunCreate(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    challenge_id: int
    submitted_code: str = Field(min_length=1)


class RunRead(BaseModel):
    outcome: ExecutionOutcome
    test_results: list[TestCaseResult] = Field(default_factory=list)
    passed_tests: int = 0
    total_tests: int = 0
    error: str | None = None
    remaining_seconds: int = 0
    run_count: int = 0


class RubricScoreRead(BaseModel):
    dimension: str
    score: float
    feedback: str


class SubmissionRead(BaseModel):
    id: int
    challenge_id: int
    session_id: str
    submitted_code: str
    status: SubmissionStatus
    score: float | None
    passed: bool | None
    scores: list[RubricScoreRead] = Field(default_factory=list)
    test_results: list[TestCaseResult] = Field(default_factory=list)
    total_tests: int = 0
    passed_tests: int = 0
    hidden_tests_count: int = 0
    error: str | None = None
    evaluation_score: int | None = None
    evaluation_status: str | None = None
    breakdown: ScoreBreakdown | None = None
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    next_difficulty: str | None = None
    feedback_summary: str | None = None
    created_at: datetime
    updated_at: datetime


class SessionSubmissionsRead(BaseModel):
    session_id: str
    submissions: list[SubmissionRead]


class SessionCompletionRead(BaseModel):
    """Response after a candidate formally completes an assessment session."""

    session_id: str
    status: str
    completed_at: datetime
    challenges_submitted: int
    challenges_total: int
    unsubmitted_challenge_ids: list[int]
    integrity_score: int | None = None
    integrity_risk_level: str | None = None
    message: str = ""


class TestCaseDTO(BaseModel):
    """Internal DTO passed to the E2B execution layer."""

    id: str
    input: str
    expected_output: str
    is_hidden: bool = False
    weight: float = 1.0


class SandboxResultsPayload(BaseModel):
    """Structured artifact written by the sandbox runner."""

    schema_version: int = Field(ge=1)
    results: list[TestCaseResult]
