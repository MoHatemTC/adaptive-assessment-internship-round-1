from typing import Any, Dict, List, Optional

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


class MCQAnswerRequest(BaseModel):
    """Request body for the adaptive MCQ answer endpoint.

    ``selected_option`` is the option *label* (for example ``"A"``), matching how
    options are stored and served — there is no numeric option id in this schema.
    """

    question_id: int
    selected_option: str = Field(..., description="The selected option label, e.g. 'A'")
    question_index: int = Field(..., ge=0)
    total_questions: int = Field(default=5, ge=1)
    learner_id: Optional[str] = None
    learner_profile: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional learner context for question generation"
    )
    admin_config: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional admin/blueprint config for generation"
    )


class MCQNextOption(BaseModel):
    """A learner-safe option for the next question — label and text only.

    Deliberately omits ``is_correct`` so the answer is never leaked.
    """

    label: str
    text: str


class MCQNextQuestion(BaseModel):
    """The next question to present, with no grading detail.

    ``dimension`` is the question's *target* skill category (not a score) and
    ``difficulty`` is the tier — neither is a grading result.
    """

    id: int
    question_text: str
    difficulty: str
    dimension: Optional[str] = None
    options: List[MCQNextOption]


class MCQAnswerResponse(BaseModel):
    """Learner-safe response for the adaptive answer endpoint.

    Carries only the next question (if any) and a completion flag. It never
    contains score, correctness, pass/fail, grading feedback, dimension scores,
    or memory card contents.
    """

    next_question: Optional[MCQNextQuestion] = None
    is_complete: bool