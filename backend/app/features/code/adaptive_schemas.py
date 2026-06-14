"""Typed contracts for the Sprint 2 adaptive coding loop."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.challenges.schemas import PlatformChallengeConfig, UserProfile
from shared.schemas.blueprint import DifficultyLevel


class CodeToolInput(BaseModel):
    """Agent-facing input for one adaptive code turn."""

    platform_session_id: str | None = None
    code_session_id: str
    learner_profile: UserProfile
    admin_config: PlatformChallengeConfig
    target_difficulty: DifficultyLevel | str
    target_category: str | None = None
    target_language: str | None = None
    challenge_id: int | None = None
    submitted_code: str | None = None


class CodeToolOutput(BaseModel):
    """Silent structured output — no learner-facing scores."""

    challenge_id: int
    objective_pass_rate: float = Field(ge=0, le=1)
    efficiency_score: float = Field(ge=0, le=1)
    rubric_score: float = Field(ge=0, le=1)
    dimension_signals: dict[str, float]
    memory_card_id: int
    passed: bool
    execution_outcome: str


class LearnerCodeAnalysis(BaseModel):
    """Aggregated estimates from memory cards for one code session."""

    dimension_estimates: dict[str, float]
    strong_problem_types: list[str]
    weak_problem_types: list[str]
    average_pass_rate: float
    average_efficiency: float
    average_rubric_score: float
    turns_completed: int


class AdaptationDecision(BaseModel):
    """Internal decision for the next challenge slot."""

    next_difficulty: str
    next_category: str
    next_language: str
    rationale: str


class AdaptiveSubmitRequest(BaseModel):
    challenge_id: int
    submitted_code: str = Field(min_length=1)


class AdaptiveSubmitResponse(BaseModel):
    """Silent submit response — no scores exposed to learners."""

    session_id: str
    status: str
    turns_completed: int
    total_questions: int
    session_complete: bool
    message: str = "Submitted — preparing next challenge…"


class AdaptiveSessionRead(BaseModel):
    """Adaptive session view with loop metadata."""

    session_id: str
    status: str
    adaptive: bool = True
    total_remaining_seconds: int
    expires_at: str
    turns_completed: int
    total_questions: int
    current_difficulty: str
    challenges: list  # SessionChallengeRead at runtime; kept loose to avoid circular imports
    generation_notes: str = ""
