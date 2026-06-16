from typing import List, Optional

from pydantic import BaseModel, Field


class MCQOption(BaseModel):
    label: str = Field(..., description="Option label, such as A, B, C, or D")
    text: str = Field(..., description="Option text shown to the learner")


class MCQCreateRequest(BaseModel):
    question_text: str = Field(..., description="Question prompt shown to the learner")
    difficulty: str = Field(default="easy", description="Question difficulty")
    correct_option: str = Field(
        ...,
        description="Identifier of the correct option (stored server-side only)",
    )
    options: List[MCQOption] = Field(..., description="Selectable answer options")


class MCQQuestionResponse(BaseModel):
    id: int
    question_text: str
    options: List[MCQOption]
    difficulty: str


class MCQSubmitRequest(BaseModel):
    question_id: int
    session_id: str = Field(..., description="Owning assessment session id")
    selected_option: str
    learner_id: Optional[str] = None


class MCQSubmitResponse(BaseModel):
    """Silent acknowledgement that an answer was received.

    Grading is silent: ``is_correct`` and ``score`` are persisted server-side
    but never returned to the learner.
    """

    received: bool = True
    question_id: int