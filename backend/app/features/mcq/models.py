"""SQLAlchemy 2.0 ORM models for the MCQ feature.

These models use the SQLAlchemy 2.0 declarative style (``Mapped[...]`` +
``mapped_column()``) on the kernel's :class:`~app.core.database.Base`. The
correct answer (:attr:`MCQQuestion.correct_option`) and the grading columns on
:class:`MCQResponse` (:attr:`~MCQResponse.is_correct`, :attr:`~MCQResponse.score`,
:attr:`~MCQResponse.grading_feedback`) are stored server-side only — they are
persisted for the LLM judge, the shared adaptation agent, and admin reporting,
and must never be returned to the learner.

:attr:`MCQQuestion.dimension` and the :attr:`MCQResponse.question` relationship
exist so the shared adaptation agent's ``_fetch_mcq_answers`` can read
``response.score``, ``response.grading_feedback``, and
``response.question.dimension.value`` to drive platform-wide adaptation.
"""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import relationship

from app.core.database import Base, Mapped, mapped_column


class SkillDimension(str, enum.Enum):
    """The five platform skill dimensions a question can target.

    Values mirror :data:`app.shared.schemas.memory.DimensionName` exactly so
    that ``dimension.value`` is a valid normalized dimension name for the
    shared adaptation agent.
    """

    thinking = "thinking"
    soft = "soft"
    work = "work"
    digital_ai = "digital_ai"
    growth = "growth"


class MCQQuestion(Base):
    """An MCQ question and its correct answer.

    The correct option is stored in the backend only and must not be exposed
    directly to the frontend or the learner.

    Attributes:
        id: Surrogate primary key.
        question_text: The question prompt shown to the learner.
        difficulty: Difficulty label (for example ``"easy"``).
        correct_option: Identifier of the correct option (kept server-side).
        dimension: Skill dimension this question targets. Read by the shared
            adaptation agent via ``response.question.dimension.value``. Nullable
            because questions created before this column existed have no value.
        created_at: Server-set timestamp of row insertion.
    """

    __tablename__ = "mcq_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="easy"
    )
    correct_option: Mapped[str] = mapped_column(String(10), nullable=False)
    dimension: Mapped[SkillDimension | None] = mapped_column(
        SAEnum(SkillDimension, name="mcq_skill_dimension"),
        nullable=True,
        comment=(
            "Skill dimension this question targets "
            "(thinking/soft/work/digital_ai/growth)."
        ),
    )
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
        score: Silent grading score 0.0–1.0, or ``None`` until graded. Read by
            the shared adaptation agent (server-side). Never exposed to learner.
        grading_feedback: Internal grading feedback. Read by the shared
            adaptation agent (server-side). Never exposed to the learner.
        question: Relationship to the answered question, used by the shared
            adaptation agent to read ``question.dimension``.
        created_at: Server-set timestamp of row insertion.
    """

    __tablename__ = "mcq_responses"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("mcq_questions.id"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        # FK deferred until assessment_sessions table exists
    )
    learner_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    selected_option: Mapped[str] = mapped_column(String(10), nullable=False)
    is_correct: Mapped[bool] = mapped_column(nullable=False)
    score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Silent grading score 0.0-1.0. Never exposed to learner.",
    )
    grading_feedback: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Internal grading feedback. Never exposed to learner.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    question: Mapped["MCQQuestion"] = relationship("MCQQuestion", lazy="selectin")
