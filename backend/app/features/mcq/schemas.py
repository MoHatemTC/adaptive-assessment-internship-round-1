from typing import Literal

from pydantic import BaseModel, Field


DifficultyLevel = Literal["beginner", "intermediate", "advanced"]
SkillDimension = Literal["Thinking", "Soft", "Work", "Digital/AI", "Growth"]


class MCQOption(BaseModel):
    label: str = Field(..., description="Option label, such as A, B, C, or D")
    text: str = Field(..., description="Option text shown to the learner")


class MCQCreateRequest(BaseModel):
    question_text: str = Field(..., description="Question prompt shown to the learner")
    difficulty: DifficultyLevel = Field(
        default="beginner",
        description="Question difficulty: beginner, intermediate, or advanced",
    )
    dimension: SkillDimension | None = Field(
        default=None,
        description="Primary skill dimension measured by this question",
    )
    correct_option: str = Field(
        ...,
        description="Identifier of the correct option stored server-side only",
    )
    options: list[MCQOption] = Field(..., description="Selectable answer options")


class MCQQuestionResponse(BaseModel):
    id: int
    question_text: str
    options: list[MCQOption]
    difficulty: DifficultyLevel
    dimension: SkillDimension | None = None


class MCQSubmitRequest(BaseModel):
    question_id: int
    session_id: str = Field(
        ...,
        min_length=36,
        max_length=36,
        description="Owning assessment session UUID",
    )
    question_index: int = Field(
        ...,
        ge=0,
        description="Position of this question in the blueprint, 0-indexed",
    )
    selected_option: str = Field(
        ...,
        description="Learner selected option label",
    )


class MCQSubmitResponse(BaseModel):
    """Silent acknowledgement that an answer was received."""

    received: bool = True
    question_id: int


class MCQAdaptiveSubmitRequest(BaseModel):
    question_id: int
    session_id: str = Field(
        ...,
        min_length=36,
        max_length=36,
        description="Owning assessment session UUID",
    )
    question_index: int = Field(
        ...,
        ge=0,
        description="Position of this question in the blueprint, 0-indexed",
    )
    selected_option: str = Field(
        ...,
        description="Learner selected option label",
    )
    learner_profile: dict | None = Field(
        default=None,
        description="Optional learner profile context from the shared platform",
    )
    admin_config: dict | None = Field(
        default=None,
        description="Optional admin/blueprint config for adaptation",
    )


class MCQAdaptiveSubmitResponse(BaseModel):
    """Adaptive submit response without correctness or score."""

    received: bool = True
    question_id: int
    next_plan: dict
    next_question: MCQQuestionResponse
