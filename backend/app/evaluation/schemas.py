"""Shared schemas for LLM-driven challenge evaluation."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScoreWeights(BaseModel):
    """Admin-configurable dimension weights (must sum to 1.0)."""

    correctness: float = Field(default=0.35, ge=0, le=1)
    completeness: float = Field(default=0.15, ge=0, le=1)
    code_quality: float = Field(default=0.20, ge=0, le=1)
    performance: float = Field(default=0.15, ge=0, le=1)
    creativity: float = Field(default=0.08, ge=0, le=1)
    documentation: float = Field(default=0.07, ge=0, le=1)


class ScoringSettings(BaseModel):
    """Scoring configuration (admin-defined; defaults until admin API lands)."""

    max_score: int = Field(default=100, ge=1, le=1000)
    passing_threshold: int = Field(default=60, ge=0, le=1000)
    weights: ScoreWeights = Field(default_factory=ScoreWeights)


class AIEvaluationSettings(BaseModel):
    """AI evaluation behaviour (admin-defined)."""

    strictness: str = Field(default="balanced")  # lenient | balanced | strict
    feedback_verbosity: str = Field(default="detailed")  # brief | detailed
    hallucination_safeguards: bool = True
    allowed_criteria: list[str] = Field(
        default_factory=lambda: [
            "correctness",
            "completeness",
            "code_quality",
            "performance",
            "creativity",
            "documentation",
        ]
    )


class PlatformEvaluationConfig(BaseModel):
    """Subset of admin platform config consumed by the LLM evaluator."""

    scoring: ScoringSettings = Field(default_factory=ScoringSettings)
    ai_evaluation: AIEvaluationSettings = Field(default_factory=AIEvaluationSettings)


class ScoreBreakdown(BaseModel):
    """Point breakdown on a 0–max_score scale."""

    correctness: int = 0
    completeness: int = 0
    code_quality: int = 0
    performance: int = 0
    creativity: int = 0
    documentation: int = 0


class DimensionScores(BaseModel):
    """Normalized 0.0–1.0 scores per dimension."""

    correctness: float = Field(ge=0, le=1)
    completeness: float = Field(ge=0, le=1)
    code_quality: float = Field(ge=0, le=1)
    performance: float = Field(ge=0, le=1)
    creativity: float = Field(ge=0, le=1)
    documentation: float = Field(ge=0, le=1)


class EvaluationResult(BaseModel):
    """Full evaluation payload returned by the LLM evaluator."""

    challenge_id: int | str
    score: int
    status: str
    breakdown: ScoreBreakdown
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    next_difficulty: str = "same"
    dimension_scores: DimensionScores
    feedback_summary: str = ""


class CodeEvaluationContext(BaseModel):
    """Inputs for evaluating a programming challenge submission."""

    challenge_id: int
    title: str
    description: str
    submitted_code: str
    language: str = "python"
    correctness_ratio: float = Field(ge=0, le=1)
    performance_ratio: float = Field(ge=0, le=1)
    passed_tests: int = 0
    total_tests: int = 0
    execution_error: str | None = None
