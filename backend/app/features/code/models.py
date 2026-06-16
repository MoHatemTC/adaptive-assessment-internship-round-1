"""SQLModel entities for the code execution feature."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, Float, Index, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, Relationship

from app.core.database import Base, Mapped, SQLModel, TimestampMixin, mapped_column

if TYPE_CHECKING:
    pass


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
    language: str = Field(default="python", max_length=32)
    time_limit_seconds: int = Field(default=20, ge=1, le=300)

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
    session_id: str = Field(max_length=64, index=True)
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


class CodeMemoryCard(Base):
    """Coding-tool detail row backing one platform ``memory_cards`` entry.

    Written by Layer 2 (memory card extraction) alongside the shared
    ``memory_cards`` row. Holds the code-specific evidence (sandbox score and
    the approach/efficiency feedback) that the platform table does not carry.

    Attributes:
        id: Surrogate primary key.
        session_id: Owning assessment session UUID.
        question_index: Zero-based position in the assessment blueprint.
        submission_id: PK of the originating ``code_submissions`` row.
        memory_card_id: PK of the linked platform ``memory_cards`` row.
        sandbox_score: Weighted E2B test-pass score in ``[0, 1]``.
        approach_feedback: LLM rubric feedback on solution approach.
        efficiency_feedback: LLM rubric feedback on solution efficiency.
        created_at: Server-set timestamp of row insertion.
    """

    __tablename__ = "code_memory_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    # FK deferred until assessment_sessions table exists
    question_index: Mapped[int] = mapped_column(nullable=False)
    submission_id: Mapped[int] = mapped_column(nullable=False)
    # FK to code_submissions.id (enforced at the DB level by the migration)
    memory_card_id: Mapped[int] = mapped_column(nullable=False)
    # FK to platform memory_cards.id (deferred, cross-metadata)
    sandbox_score: Mapped[float] = mapped_column(Float, nullable=False)
    approach_feedback: Mapped[str] = mapped_column(Text, nullable=False)
    efficiency_feedback: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
