"""Assessment blueprint contracts (admin → agent)."""

from enum import Enum

from pydantic import BaseModel, Field


class QuestionType(str, Enum):
    MCQ = "mcq"
    OPEN_ENDED = "open_ended"
    CODE = "code"
    DIAGRAM = "diagram"
    VOICE = "voice"


class DifficultyLevel(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class QuestionPlan(BaseModel):
    question_type: QuestionType
    topic: str
    difficulty: DifficultyLevel
    estimated_duration_seconds: int = Field(ge=30)
    rubric_id: str | None = None


class Blueprint(BaseModel):
    assessment_id: str
    title: str
    total_questions: int = Field(ge=1)
    skill_dimensions: list[str]
    question_plans: list[QuestionPlan]
    adaptive: bool = True
    time_limit_minutes: int | None = None
