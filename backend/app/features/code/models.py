"""SQLModel entities for the code execution feature."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, Enum as SAEnum, Float, Index, Text
from sqlmodel import Field, Relationship

from app.core.database import SQLModel, TimestampMixin
from app.features.code.constants import SupportedLanguage
from app.features.code.timers import utcnow

if TYPE_CHECKING:
    pass


class SessionStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"


class SubmissionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CodeChallenge(SQLModel, TimestampMixin, table=True):
    __tablename__ = "code_challenges"

    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(max_length=255)
    description: str = Field(sa_column=Column(Text))
    starter_code: str = Field(sa_column=Column(Text))
    language: str = Field(
        default=SupportedLanguage.PYTHON.value,
        max_length=32,
    )
    time_limit_seconds: int = Field(default=20, ge=1, le=300)
    candidate_time_seconds: int = Field(default=1200, ge=60, le=7200)

    test_cases: list["TestCase"] = Relationship(back_populates="challenge")
    submissions: list["CodeSubmission"] = Relationship(back_populates="challenge")


class TestCase(SQLModel, TimestampMixin, table=True):
    __tablename__ = "code_test_cases"
    __table_args__ = (Index("ix_code_test_cases_challenge_id", "challenge_id"),)

    id: int | None = Field(default=None, primary_key=True)
    challenge_id: int = Field(foreign_key="code_challenges.id", nullable=False)
    input: str = Field(sa_column=Column(Text))
    expected_output: str = Field(sa_column=Column(Text))
    is_hidden: bool = Field(default=False)
    weight: float = Field(default=1.0, sa_column=Column(Float, nullable=False))

    challenge: CodeChallenge | None = Relationship(back_populates="test_cases")


class CodeSubmission(SQLModel, TimestampMixin, table=True):
    __tablename__ = "code_submissions"
    __table_args__ = (
        Index("ix_code_submissions_challenge_id", "challenge_id"),
        Index("ix_code_submissions_session_id", "session_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    challenge_id: int = Field(foreign_key="code_challenges.id", nullable=False)
    session_id: str = Field(max_length=64)
    submitted_code: str = Field(sa_column=Column(Text))
    status: SubmissionStatus = Field(
        default=SubmissionStatus.PENDING,
        sa_column=Column(
            SAEnum(SubmissionStatus, native_enum=False, length=32),
            nullable=False,
        ),
    )
    score: float | None = Field(default=None)
    passed: bool | None = Field(default=None)
    grading_metadata: str | None = Field(default=None, sa_column=Column(Text))

    challenge: CodeChallenge | None = Relationship(back_populates="submissions")


class CodeAssessmentSession(SQLModel, TimestampMixin, table=True):
    __tablename__ = "code_assessment_sessions"
    __table_args__ = (Index("ix_code_assessment_sessions_session_id", "session_id", unique=True),)

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(max_length=64, unique=True)
    profile_json: str = Field(sa_column=Column(Text, nullable=False))
    config_snapshot: str = Field(sa_column=Column(Text, nullable=False))
    status: SessionStatus = Field(
        default=SessionStatus.ACTIVE,
        sa_column=Column(
            SAEnum(SessionStatus, native_enum=False, length=32),
            nullable=False,
        ),
    )
    started_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    completed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    analysis_json: str | None = Field(default=None, sa_column=Column(Text))

    attempts: list["CodeChallengeAttempt"] = Relationship(back_populates="assessment_session")


class SessionAuditEvent(SQLModel, table=True):
    """Immutable audit trail for session lifecycle events."""

    __tablename__ = "session_audit_events"
    __table_args__ = (Index("ix_session_audit_events_session_id", "session_id"),)

    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(max_length=64)
    event_type: str = Field(max_length=64)
    actor: str = Field(max_length=32)
    metadata_json: str | None = Field(default=None, sa_column=Column(Text))


class CodeChallengeAttempt(SQLModel, TimestampMixin, table=True):
    __tablename__ = "code_challenge_attempts"
    __table_args__ = (
        Index("ix_code_challenge_attempts_session_id", "assessment_session_id"),
        Index("ix_code_challenge_attempts_challenge_id", "challenge_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    assessment_session_id: int = Field(foreign_key="code_assessment_sessions.id", nullable=False)
    challenge_id: int = Field(foreign_key="code_challenges.id", nullable=False)
    started_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    submitted_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    graded_submission_id: int | None = Field(
        default=None,
        foreign_key="code_submissions.id",
        nullable=True,
    )
    e2b_sandbox_id: str | None = Field(default=None, max_length=128)
    run_count: int = Field(default=0, ge=0)

    assessment_session: CodeAssessmentSession | None = Relationship(back_populates="attempts")


class CodeMemoryCard(SQLModel, table=True):
    """Silent evaluation snapshot for adaptive analysis (one row per graded turn)."""

    __tablename__ = "code_memory_cards"
    __table_args__ = (
        Index("ix_code_memory_cards_code_session_id", "code_session_id"),
        Index("ix_code_memory_cards_platform_session_id", "platform_session_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    platform_session_id: str | None = Field(default=None, sa_column=Column(Text))
    code_session_id: str = Field(max_length=64)
    challenge_id: int = Field(foreign_key="code_challenges.id", nullable=False)
    problem_type: str = Field(max_length=64)
    difficulty: str = Field(max_length=32)
    language: str = Field(max_length=32)
    pass_rate: float = Field(sa_column=Column(Float, nullable=False))
    efficiency: float = Field(sa_column=Column(Float, nullable=False))
    rubric_score: float = Field(sa_column=Column(Float, nullable=False))
    dimension_signals_json: str = Field(sa_column=Column(Text, nullable=False))
    passed: bool = Field(default=False)
    test_results_json: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: utcnow(),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class CodeRun(SQLModel, TimestampMixin, table=True):
    __tablename__ = "code_runs"
    __table_args__ = (Index("ix_code_runs_attempt_id", "attempt_id"),)

    id: int | None = Field(default=None, primary_key=True)
    attempt_id: int = Field(foreign_key="code_challenge_attempts.id", nullable=False)
    outcome: str = Field(max_length=32)
    passed_tests: int = Field(default=0, ge=0)
    total_tests: int = Field(default=0, ge=0)
    error: str | None = Field(default=None, sa_column=Column(Text))
