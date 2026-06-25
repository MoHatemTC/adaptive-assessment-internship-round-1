from typing import Optional

from pydantic import BaseModel, Field


class DiagramCreateRequest(BaseModel):
    svg_content: str
    prompt: str
    correct_label: str
    rubric: str
    difficulty: str = "easy"
    dimension: Optional[str] = None


class DiagramQuestionResponse(BaseModel):
    """Learner-safe question shape. correct_label and rubric are intentionally absent."""

    id: int
    svg_content: str
    prompt: str
    difficulty: str
    dimension: Optional[str] = None


class DiagramAnswerRequest(BaseModel):
    question_id: int
    answer_text: str = Field(..., min_length=1, max_length=500)
    question_index: int = Field(..., ge=0)
    total_questions: int = Field(default=5, ge=1)
    learner_id: Optional[str] = None
    learner_profile: Optional[dict] = None
    admin_config: Optional[dict] = None


class DiagramNextQuestion(BaseModel):
    """Next question — same learner-safe shape as DiagramQuestionResponse."""

    id: int
    svg_content: str
    prompt: str
    difficulty: str
    dimension: Optional[str] = None


class DiagramAnswerResponse(BaseModel):
    """Learner-safe response. Never includes score, feedback, or correct_label."""

    next_question: Optional[DiagramNextQuestion] = None
    is_complete: bool
