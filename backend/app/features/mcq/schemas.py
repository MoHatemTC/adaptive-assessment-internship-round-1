from typing import List, Optional

from pydantic import BaseModel, Field


class MCQOption(BaseModel):
    label: str = Field(..., description="Option label, such as A, B, C, or D")
    text: str = Field(..., description="Option text shown to the learner")


class MCQGenerateRequest(BaseModel):
    topic: str = Field(default="Python basics", description="Assessment topic")
    difficulty: str = Field(default="easy", description="Question difficulty")
    question_count: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Number of MCQ questions requested",
    )


class MCQQuestionResponse(BaseModel):
    id: int
    question_text: str
    options: List[MCQOption]
    difficulty: str


class MCQSubmitRequest(BaseModel):
    question_id: int
    selected_option: str
    learner_id: Optional[str] = None


class MCQSubmitResponse(BaseModel):
    question_id: int
    selected_option: str
    is_correct: bool
    score: int