"""SQLAlchemy 2.0 ORM models for the MCQ feature.

These models follow the Masaar unified database schema.

Important rules:
- MCQ response rows store only learner submissions.
- No score, correctness, or grading output is stored on mcq_responses.
- Grading output belongs to the shared platform grading layer.
- session_id is stored as String(36).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func

from app.core.database import Base, Mapped, mapped_column


class MCQQuestion(Base):
    """Stored MCQ question.

    correct_option is stored server-side only and must never be exposed
    to the learner-facing API.
    """

    __tablename__ = "mcq_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="beginner"
    )
    correct_option: Mapped[str] = mapped_column(String(10), nullable=False)
    dimension: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MCQOption(Base):
    """A selectable answer option belonging to an MCQ question."""

    __tablename__ = "mcq_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("mcq_questions.id"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(10), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)


class MCQResponse(Base):
    """A learner's submitted MCQ answer.

    This table stores learner submissions only.
    It must not store score, correctness, or correct_option.
    """

    __tablename__ = "mcq_responses"

    id: Mapped[int] = mapped_column(primary_key=True)

    session_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True
    )  # FK deferred until assessment_sessions table exists

    question_id: Mapped[int] = mapped_column(
        ForeignKey("mcq_questions.id"), nullable=False
    )
    question_index: Mapped[int] = mapped_column(nullable=False)
    selected_option: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
