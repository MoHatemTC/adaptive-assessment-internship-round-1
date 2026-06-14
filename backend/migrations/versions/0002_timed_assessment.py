"""Timed assessment: admin config, sessions, attempts, candidate timers.

Revision ID: 0002_timed_assessment
Revises: 0001_code
Create Date: 2026-06-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_timed_assessment"
down_revision: Union[str, None] = "0001_code"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_code_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column(
        "code_challenges",
        sa.Column("candidate_time_seconds", sa.Integer(), server_default="1200", nullable=False),
    )

    op.create_table(
        "code_assessment_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("profile_json", sa.Text(), nullable=False),
        sa.Column("config_snapshot", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index(
        "ix_code_assessment_sessions_session_id",
        "code_assessment_sessions",
        ["session_id"],
        unique=True,
    )

    op.create_table(
        "code_challenge_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assessment_session_id", sa.Integer(), nullable=False),
        sa.Column("challenge_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("graded_submission_id", sa.Integer(), nullable=True),
        sa.Column("e2b_sandbox_id", sa.String(length=128), nullable=True),
        sa.Column("run_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["assessment_session_id"], ["code_assessment_sessions.id"]),
        sa.ForeignKeyConstraint(["challenge_id"], ["code_challenges.id"]),
        sa.ForeignKeyConstraint(["graded_submission_id"], ["code_submissions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_code_challenge_attempts_session_id",
        "code_challenge_attempts",
        ["assessment_session_id"],
    )
    op.create_index(
        "ix_code_challenge_attempts_challenge_id",
        "code_challenge_attempts",
        ["challenge_id"],
    )

    op.create_table(
        "code_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("passed_tests", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_tests", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["attempt_id"], ["code_challenge_attempts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_runs_attempt_id", "code_runs", ["attempt_id"])


def downgrade() -> None:
    op.drop_index("ix_code_runs_attempt_id", table_name="code_runs")
    op.drop_table("code_runs")
    op.drop_index("ix_code_challenge_attempts_challenge_id", table_name="code_challenge_attempts")
    op.drop_index("ix_code_challenge_attempts_session_id", table_name="code_challenge_attempts")
    op.drop_table("code_challenge_attempts")
    op.drop_index("ix_code_assessment_sessions_session_id", table_name="code_assessment_sessions")
    op.drop_table("code_assessment_sessions")
    op.drop_column("code_challenges", "candidate_time_seconds")
    op.drop_table("platform_code_config")
