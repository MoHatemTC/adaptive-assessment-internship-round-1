"""Shared Pydantic v2 types for the adaptive loop.

Every tool and every agent imports from here. No tool defines its own
versions of these types.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

ToolType = Literal["voice", "mcq", "diagram", "coding"]
DifficultyLevel = Literal["beginner", "intermediate", "advanced"]
DimensionName = Literal["thinking", "soft", "work", "digital_ai", "growth"]


class DimensionSignals(BaseModel):
    """Which of the 5 skill dimensions were engaged by this response."""

    thinking: bool = False
    soft: bool = False
    work: bool = False
    digital_ai: bool = False
    growth: bool = False


class DimensionScore(BaseModel):
    """Whole integers 1–10 only. None means N/A for this tool/question."""

    thinking: Optional[int] = Field(None, ge=1, le=10)
    soft: Optional[int] = Field(None, ge=1, le=10)
    work: Optional[int] = Field(None, ge=1, le=10)
    digital_ai: Optional[int] = Field(None, ge=1, le=10)
    growth: Optional[int] = Field(None, ge=1, le=10)

    @field_validator("thinking", "soft", "work", "digital_ai", "growth", mode="before")
    @classmethod
    def _whole_number(cls, value: object) -> object:
        """Reject non-integer values so floats never sneak in as scores.

        Args:
            value: The raw field value before Pydantic type coercion.

        Returns:
            The original value unchanged if it passes validation.

        Raises:
            ValueError: If value is not None and not an int.
        """
        if value is not None and not isinstance(value, int):
            raise ValueError("score must be a whole integer, not a float or other type")
        return value


class RubricDimension(BaseModel):
    """A single scored dimension from an LLM rubric evaluation.

    Attributes:
        name: Dimension label (e.g. ``"clarity"``).
        score: Normalized score in ``[0.0, 1.0]``.
        feedback: Textual justification from the LLM judge.
    """

    name: str
    score: float = Field(ge=0.0, le=1.0)
    feedback: str


class RubricScores(BaseModel):
    """LLM rubric output. Written to grade_results.rubric_scores. Never
    shown to the learner during the session.

    Attributes:
        dimensions: Per-dimension breakdown from the LLM judge.
        overall: Aggregate normalized score in ``[0.0, 1.0]``.
    """

    dimensions: list[RubricDimension]
    overall: float = Field(ge=0.0, le=1.0)


class MemoryCardCreate(BaseModel):
    """Input to the Memory Card Extractor (Layer 6). One card per response.

    Attributes:
        session_id: Owning assessment session UUID.
        tool_type: Which tool produced this response.
        question_index: Zero-based position in the assessment blueprint.
        difficulty: Difficulty tier of the question.
        evidence_summary: Human-readable insight extracted from the response.
        dimension_signals: Which of the 5 dimensions were engaged.
        passed: Whether the response cleared the pass threshold.
    """

    session_id: str
    tool_type: ToolType
    question_index: int = Field(ge=0)
    difficulty: DifficultyLevel
    evidence_summary: str
    dimension_signals: DimensionSignals
    passed: bool


class MemoryCardRead(MemoryCardCreate):
    """ORM-hydrated view of a memory card, including database-assigned fields.

    Attributes:
        id: Surrogate primary key assigned by the database.
        created_at: Server-set timestamp of row insertion.
    """

    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SkillDimensionScoreCreate(BaseModel):
    """Written by Skill Taxonomy Analysis (Layer 7). One row per question
    per session.

    Attributes:
        session_id: Owning assessment session UUID.
        question_index: Zero-based position in the assessment blueprint.
        tool_type: Which tool produced the question.
        thinking: Reasoning score 1–10, or None if N/A.
        soft: Interpersonal score 1–10, or None if N/A.
        work: Execution score 1–10, or None if N/A.
        digital_ai: Tool-use score 1–10, or None if N/A.
        growth: Learning agility score 1–10, or None if N/A.
    """

    session_id: str
    question_index: int = Field(ge=0)
    tool_type: ToolType
    thinking: Optional[int] = Field(None, ge=1, le=10)
    soft: Optional[int] = Field(None, ge=1, le=10)
    work: Optional[int] = Field(None, ge=1, le=10)
    digital_ai: Optional[int] = Field(None, ge=1, le=10)
    growth: Optional[int] = Field(None, ge=1, le=10)

    @field_validator("thinking", "soft", "work", "digital_ai", "growth", mode="before")
    @classmethod
    def _whole_number(cls, value: object) -> object:
        """Reject non-integer values so floats never sneak in as scores.

        Args:
            value: The raw field value before Pydantic type coercion.

        Returns:
            The original value unchanged if it passes validation.

        Raises:
            ValueError: If value is not None and not an int.
        """
        if value is not None and not isinstance(value, int):
            raise ValueError("score must be a whole integer, not a float or other type")
        return value


class AdaptiveContract(BaseModel):
    """Output of the Adaptive Contract Layer (Layer 8). Passed directly
    to the Generator Agent as context. Never persisted to the database.

    Attributes:
        session_id: Owning assessment session UUID.
        question_index: Zero-based position of the *next* question to generate.
        tool_type: Tool type for the next question.
        difficulty: Difficulty tier for the next question.
        focus_dimension: Optional dimension to concentrate on.
        stop: Whether the session should end instead of generating a question.
        memory_summary: Narrative summary of performance so far.
        cumulative_scores: Aggregated dimension scores across all questions.
    """

    session_id: str
    question_index: int = Field(ge=0)
    tool_type: ToolType
    difficulty: DifficultyLevel
    focus_dimension: Optional[DimensionName] = None
    stop: bool = False
    memory_summary: str = ""
    cumulative_scores: DimensionScore = Field(default_factory=DimensionScore)
