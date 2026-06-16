"""SQLAlchemy 2.0 ORM models for platform session management and grading.

Four platform tables live here:

* :class:`AssessmentSession` — one row per learner sitting of an assessment.
* :class:`GradeResult` — one graded response per tool question.
* :class:`MemoryCard` — one evidence card per response (input to Layer 7).
* :class:`SkillDimensionScore` — 5-dimension scores per question (output of Layer 7).
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, SmallInteger, String, Text, func

from app.core.database import Base, Mapped, mapped_column


class AssessmentSession(Base):
    """A single learner sitting of an assessment.

    Created when a learner starts an assessment. The ``id`` (UUID) is the
    ``session_id`` that flows through every tool table in the system.

    Attributes:
        id: UUID primary key — the platform session UUID used everywhere.
        assessment_id: FK to the parent :class:`~app.admin.models.Assessment`.
        learner_profile_json: JSON learner context passed to the Generator Agent.
        status: Lifecycle state.
        code_session_id: Bridge to the coding tool's internal ``assess-*`` ID.
        started_at: Set when the learner begins the first question.
        completed_at: Set on completion or expiry.
        created_at: Server-set timestamp of row insertion.
        updated_at: Server-set timestamp of last update.
    """

    __tablename__ = "assessment_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    assessment_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    # FK deferred until assessments table exists
    learner_profile_json: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON: {name, role, level, target_skills, consent_given}
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # "pending" / "active" / "completed" / "expired" / "flagged"
    code_session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Bridge to coding tool's internal assess-* session ID
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GradeResult(Base):
    """One graded question response. Written by the grading layer (Layer 5).

    Written after each answer. The LLM judge score is NULL until the judge
    runs at end of sprint. Grading output must never be written back to the
    tool's own response table.

    Attributes:
        id: Surrogate primary key.
        session_id: Owning assessment session UUID.
        tool_type: Which tool produced the response.
        tool_session_id: PK of the tool's own session row (e.g. ``voice_sessions.id``).
        question_index: Zero-based position in the assessment blueprint.
        rubric_scores: JSON of :class:`~app.shared.schemas.memory.RubricScores`.
        llm_judge_score: Aggregate score from the end-of-sprint LLM judge, or ``None``.
        created_at: Server-set timestamp of row insertion.
    """

    __tablename__ = "grade_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    # FK deferred until assessment_sessions table exists
    tool_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # "voice" / "mcq" / "diagram" / "coding"
    tool_session_id: Mapped[int] = mapped_column(nullable=False)
    # ID of the tool's own session row (e.g. voice_sessions.id)
    question_index: Mapped[int] = mapped_column(nullable=False)
    # Position in blueprint, 0-indexed
    rubric_scores: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON: RubricScores schema from app.shared.schemas.memory
    llm_judge_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # NULL until end-of-sprint LLM judge runs
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MemoryCard(Base):
    """One evidence card per response. Written by Memory Card Extractor (Layer 6).

    This is the primary input to the Skill Taxonomy Analysis layer (Layer 7).
    One card is written immediately after grading completes for each response.

    Attributes:
        id: Surrogate primary key.
        session_id: Owning assessment session UUID.
        tool_type: Which tool produced the response.
        question_index: Zero-based position in the assessment blueprint.
        difficulty: Difficulty tier of the question.
        evidence_summary: Human-readable insight extracted from the response.
        dimension_signals: JSON of :class:`~app.shared.schemas.memory.DimensionSignals`.
        passed: Whether the response cleared the pass threshold.
        created_at: Server-set timestamp of row insertion.
    """

    __tablename__ = "memory_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    # FK deferred until assessment_sessions table exists
    tool_type: Mapped[str] = mapped_column(String(20), nullable=False)
    question_index: Mapped[int] = mapped_column(nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence_summary: Mapped[str] = mapped_column(Text, nullable=False)
    dimension_signals: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON: DimensionSignals schema from app.shared.schemas.memory
    passed: Mapped[bool] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SkillDimensionScore(Base):
    """5-dimension scores per question. Written by Skill Taxonomy Analysis (Layer 7).

    One row per question per session. All scores are whole integers 1–10.
    ``None`` means the dimension is not applicable to the tool that generated
    the question. The CHECK constraint on each column is enforced at the DB level.

    Attributes:
        id: Surrogate primary key.
        session_id: Owning assessment session UUID.
        question_index: Zero-based position in the assessment blueprint.
        tool_type: Which tool produced the question.
        thinking: Reasoning score 1–10, or ``None`` for N/A.
        soft: Interpersonal score 1–10, or ``None`` for N/A.
        work: Execution score 1–10, or ``None`` for N/A.
        digital_ai: Tool-use score 1–10, or ``None`` for N/A.
        growth: Learning agility score 1–10, or ``None`` for N/A.
        created_at: Server-set timestamp of row insertion.
    """

    __tablename__ = "skill_dimension_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    # FK deferred until assessment_sessions table exists
    question_index: Mapped[int] = mapped_column(nullable=False)
    tool_type: Mapped[str] = mapped_column(String(20), nullable=False)
    thinking: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    # 1–10 whole integer or NULL for N/A
    soft: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    work: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    digital_ai: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    growth: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
