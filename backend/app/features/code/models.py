"""SQLModel entities for the code execution feature."""

from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Column, Enum as SAEnum, Float, Index, Text
from sqlmodel import Field, Relationship

from app.core.database import SQLModel, TimestampMixin

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
