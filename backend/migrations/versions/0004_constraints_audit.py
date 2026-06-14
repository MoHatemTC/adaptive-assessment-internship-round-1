"""CHECK constraints, session audit log, completed_at.

Revision ID: 0004_constraints_audit
Revises: 0003_proctoring
Create Date: 2026-06-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_constraints_audit"
down_revision: Union[str, None] = "0003_proctoring"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "code_assessment_sessions",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "session_audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_session_audit_events_session_id",
        "session_audit_events",
        ["session_id"],
    )

    op.create_check_constraint(
        "ck_code_challenges_time_limit_seconds",
        "code_challenges",
        "time_limit_seconds >= 1 AND time_limit_seconds <= 300",
    )
    op.create_check_constraint(
        "ck_code_challenges_candidate_time_seconds",
        "code_challenges",
        "candidate_time_seconds >= 60 AND candidate_time_seconds <= 7200",
    )
    op.create_check_constraint(
        "ck_code_challenges_language",
        "code_challenges",
        "language = 'python'",
    )
    op.create_check_constraint(
        "ck_code_test_cases_weight",
        "code_test_cases",
        "weight > 0 AND weight <= 100",
    )


def downgrade() -> None:
    op.drop_constraint("ck_code_test_cases_weight", "code_test_cases", type_="check")
    op.drop_constraint("ck_code_challenges_language", "code_challenges", type_="check")
    op.drop_constraint("ck_code_challenges_candidate_time_seconds", "code_challenges", type_="check")
    op.drop_constraint("ck_code_challenges_time_limit_seconds", "code_challenges", type_="check")
    op.drop_index("ix_session_audit_events_session_id", table_name="session_audit_events")
    op.drop_table("session_audit_events")
    op.drop_column("code_assessment_sessions", "completed_at")
