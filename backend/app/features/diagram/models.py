"""
models.py — SQLAlchemy ORM models for the diagram feature.

DiagramQuestion  : the item delivered to the learner
                   (image_url, prompt, rubric, difficulty)
DiagramAnswer    : the learner's text response, persisted per session
                   queryable by session_id (blueprint requirement)

Difficulty enum matches the blueprint's "difficulty progression" language.
Five skill dimensions (Thinking/Soft/Work/Digital/Growth) are stored on
the answer so the aggregation step can map results without a join.
"""

import uuid
import enum
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, Float, Integer,
    ForeignKey, DateTime, Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class Difficulty(str, enum.Enum):
    easy   = "easy"
    medium = "medium"
    hard   = "hard"


class SkillDimension(str, enum.Enum):
    """Five dimensions from the project spec."""
    thinking   = "thinking"
    soft       = "soft"
    work       = "work"
    digital_ai = "digital_ai"
    growth     = "growth"


class DiagramQuestion(Base):
    __tablename__ = "diagram_questions"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    image_url  = Column(String, nullable=False)
    prompt     = Column(Text, nullable=False)
    rubric     = Column(Text, nullable=False)
    difficulty = Column(SAEnum(Difficulty), nullable=False)
    dimension  = Column(SAEnum(SkillDimension), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    answers    = relationship("DiagramAnswer", back_populates="question")


class DiagramAnswer(Base):
    __tablename__ = "diagram_answers"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id  = Column(UUID(as_uuid=True), nullable=False, index=True)
    question_id = Column(UUID(as_uuid=True), ForeignKey("diagram_questions.id"), nullable=False)
    answer_text = Column(Text, nullable=False)

    score           = Column(Float, nullable=True)
    grading_feedback = Column(Text, nullable=True)
    graded_at       = Column(DateTime, nullable=True)

    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    question = relationship("DiagramQuestion", back_populates="answers")