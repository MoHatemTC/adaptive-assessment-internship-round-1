"""SQLAlchemy 2.0 ORM models for the diagram feature."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import relationship

from app.core.database import Base, Mapped, mapped_column


class DiagramSkillDimension(str, enum.Enum):
    thinking = "thinking"
    soft = "soft"
    work = "work"
    digital_ai = "digital_ai"
    growth = "growth"


class DiagramQuestion(Base):
    __tablename__ = "diagram_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    svg_content: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    correct_label: Mapped[str] = mapped_column(String(255), nullable=False)
    rubric: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="easy"
    )
    dimension: Mapped[DiagramSkillDimension | None] = mapped_column(
        SAEnum(DiagramSkillDimension, name="diagram_skill_dimension", create_type=False),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DiagramResponse(Base):
    __tablename__ = "diagram_responses"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("diagram_questions.id"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    learner_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="1.0 = correct, 0.0 = wrong. Never exposed to learner.",
    )
    grading_feedback: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Server-side only. Never exposed to learner.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    question: Mapped["DiagramQuestion"] = relationship(
        "DiagramQuestion", lazy="selectin"
    )
