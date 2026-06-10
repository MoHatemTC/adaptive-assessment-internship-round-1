from typing import Optional

from app.core.database import Field, SQLModel, TimestampMixin


class MCQQuestion(SQLModel, TimestampMixin, table=True):
    """
    Stores an MCQ question.

    The correct option is stored in the backend only and must not be exposed
    directly to the frontend.
    """

    __tablename__ = "mcq_questions"

    id: Optional[int] = Field(default=None, primary_key=True)
    question_text: str = Field(nullable=False)
    difficulty: str = Field(default="easy", nullable=False)
    correct_option: str = Field(nullable=False)


class MCQOption(SQLModel, table=True):
    """
    Stores MCQ answer options for a question.
    """

    __tablename__ = "mcq_options"

    id: Optional[int] = Field(default=None, primary_key=True)
    question_id: int = Field(foreign_key="mcq_questions.id", nullable=False)
    label: str = Field(nullable=False)
    text: str = Field(nullable=False)


class MCQResponse(SQLModel, TimestampMixin, table=True):
    """
    Stores the learner's selected answer and silent score.
    """

    __tablename__ = "mcq_responses"

    id: Optional[int] = Field(default=None, primary_key=True)
    question_id: int = Field(foreign_key="mcq_questions.id", nullable=False)
    learner_id: Optional[str] = Field(default=None)
    selected_option: str = Field(nullable=False)
    is_correct: bool = Field(nullable=False)
    score: int = Field(default=0, nullable=False)