import uuid
from typing import Optional
from app.core.database import Field, SQLModel, TimestampMixin


class Diagram(SQLModel, TimestampMixin, table=True):
    """
    Stores metadata for diagrams generated during learner assessments.
    """

    __tablename__ = "diagrams"

    id: Optional[uuid.UUID] = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        nullable=False,
    )
    user_id: Optional[uuid.UUID] = Field(default=None, nullable=True)
    prompt: str = Field(nullable=False)
    model_name: str = Field(default="azure/FW-Kimi-K2.6", nullable=False, max_length=255)
    image_url: Optional[str] = Field(default=None, nullable=True)
    status: str = Field(default="pending", nullable=False)


class DiagramQuestion(SQLModel, TimestampMixin, table=True):
    """
    Stores diagram question metadata and expected answer information.
    """

    __tablename__ = "diagram_questions"

    id: Optional[uuid.UUID] = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        nullable=False,
    )
    prompt_text: str = Field(nullable=False)
    difficulty: str = Field(default="easy", nullable=False, max_length=50)
    correct_answer: str = Field(nullable=False)


class DiagramOption(SQLModel, table=True):
    """
    Stores selectable diagram answer options for a diagram question.
    """

    __tablename__ = "diagram_options"

    id: Optional[uuid.UUID] = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        nullable=False,
    )
    question_id: uuid.UUID = Field(foreign_key="diagram_questions.id", nullable=False)
    label: str = Field(nullable=False)
    text: str = Field(nullable=False)


class DiagramResponse(SQLModel, TimestampMixin, table=True):
    """
    Stores learner responses for diagram questions and the computed score.
    """

    __tablename__ = "diagram_responses"

    id: Optional[uuid.UUID] = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        nullable=False,
    )
    question_id: uuid.UUID = Field(foreign_key="diagram_questions.id", nullable=False)
    learner_id: Optional[str] = Field(default=None)
    selected_option: str = Field(nullable=False)
    is_correct: bool = Field(nullable=False)
    score: int = Field(default=0, nullable=False)
