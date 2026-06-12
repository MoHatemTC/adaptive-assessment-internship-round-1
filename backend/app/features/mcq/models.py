"""SQLAlchemy 2.0 ORM models for the MCQ feature.

These models use the SQLAlchemy 2.0 declarative style (``Mapped[...]`` +
``mapped_column()``) on the kernel's :class:`~app.core.database.Base`. The
correct answer (:attr:`MCQQuestion.correct_option`) and the grading columns on
:class:`MCQResponse` (:attr:`~MCQResponse.is_correct`, :attr:`~MCQResponse.score`)
are stored server-side only — they are persisted for the LLM judge and admin
reporting and must never be returned to the learner.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func

from app.core.database import Base, Mapped, mapped_column


class MCQQuestion(Base):
    """An MCQ question and its correct answer.

    The correct option is stored in the backend only and must not be exposed
    directly to the frontend or the learner.

    Attributes:
        id: Surrogate primary key.
        question_text: The question prompt shown to the learner.
        difficulty: Difficulty label (for example ``"easy"``).
        correct_option: Identifier of the correct option (kept server-side).
        created_at: Server-set timestamp of row insertion.
    """

    __tablename__ = "mcq_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="easy"
    )
    correct_option: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MCQOption(Base):
    """A selectable answer option belonging to an :class:`MCQQuestion`.

    Attributes:
        id: Surrogate primary key.
        question_id: Foreign key to the owning question.
        label: Display label for the option (for example ``"A"``).
        text: Option text shown to the learner.
    """

    __tablename__ = "mcq_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("mcq_questions.id"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(10), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)


class MCQResponse(Base):
    """A learner's submitted answer and its silent grading result.

    :attr:`is_correct` and :attr:`score` are persisted for the LLM judge and
    admin reporting. They are never returned to the learner through the API.

    Attributes:
        id: Surrogate primary key.
        question_id: Foreign key to the answered question.
        session_id: Owning assessment session, used to query responses per
            session. Stored as a plain string for now (see note below).
        learner_id: Optional learner identifier.
        selected_option: The option identifier the learner submitted.
        is_correct: Whether the answer matched the correct option (server-side).
        score: Objective score for the answer (server-side).
        created_at: Server-set timestamp of row insertion.
    """

    __tablename__ = "mcq_responses"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("mcq_questions.id"), nullable=False
    )
    # FK to assessment_sessions.id — constraint added via migration once the
    # sessions feature is merged. Kept as a plain indexed string until then so
    # responses stay queryable per session without crashing at table creation.
    session_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    learner_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    selected_option: Mapped[str] = mapped_column(String(10), nullable=False)
    is_correct: Mapped[bool] = mapped_column(nullable=False)
    score: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
