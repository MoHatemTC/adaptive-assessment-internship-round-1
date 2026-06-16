"""Pydantic DTOs for the code execution feature."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.features.code.models import SubmissionStatus
from app.shared.schemas.memory import AdaptiveContract, DifficultyLevel

__all__ = [
    "AdaptiveContract",
    "AdaptiveSubmitRequest",
    "AdaptiveSubmitResponse",
]


class TestCaseCreate(BaseModel):
    input: str
    expected_output: str
    is_hidden: bool = False
    weight: float = Field(default=1.0, gt=0)


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
    language: str = "python"
    time_limit_seconds: int = Field(default=20, ge=1, le=300)
    test_cases: list[TestCaseCreate] = Field(min_length=1)


class ChallengeRead(BaseModel):
    id: int
    title: str
    description: str
    starter_code: str
    language: str
    time_limit_seconds: int
    test_cases: list[TestCaseRead]
    created_at: datetime
    updated_at: datetime


class ChallengeListItem(BaseModel):
    id: int
    title: str
    language: str
    time_limit_seconds: int
    created_at: datetime


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
    created_at: datetime
    updated_at: datetime


class TestCaseDTO(BaseModel):
    """Internal DTO passed to the E2B execution layer."""

    id: str
    input: str
    expected_output: str
    is_hidden: bool = False
    weight: float = 1.0


class ExecutionOutcome(str, Enum):
    SUCCESS = "success"
    SANDBOX_ERROR = "sandbox_error"
    SANDBOX_UNAVAILABLE = "sandbox_unavailable"


class AdaptiveSubmitRequest(BaseModel):
    """Input to the adaptive submit endpoint — one answered question.

    Attributes:
        challenge_id: Code challenge being answered.
        session_id: Platform assessment session UUID.
        assessment_id: Parent assessment identifier.
        submitted_code: The learner's submitted source.
        question_index: Zero-based position in the assessment blueprint.
        difficulty: Difficulty tier of the answered question.
    """

    challenge_id: int
    session_id: str = Field(min_length=1, max_length=64)
    assessment_id: str = Field(min_length=1, max_length=64)
    submitted_code: str = Field(min_length=1)
    question_index: int = Field(ge=0)
    difficulty: DifficultyLevel


class AdaptiveSubmitResponse(BaseModel):
    """Response from the adaptive submit endpoint.

    Carries only learner-safe data plus the adaptive contract for the next
    question. Raw ``grade_results`` / ``memory_cards`` are never exposed.

    Attributes:
        submission_id: PK of the persisted ``code_submissions`` row.
        passed: Whether the submission cleared the sandbox pass threshold.
        score: Weighted sandbox score in ``[0, 1]``.
        contract: The adaptive contract for the next question.
    """

    submission_id: int
    passed: bool | None
    score: float | None
    contract: AdaptiveContract
