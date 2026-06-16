"""Create platform session tables.

Revision ID: 0003_platform_sessions
Revises: 0001_voice
Create Date: 2026-06-16
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_platform_sessions"
down_revision = "0001_voice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the migration: Create assessments and assessment_sessions tables."""

    op.create_table(
        "assessments",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("blueprint_json", sa.Text(), nullable=False),
        sa.Column("tool_config", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="draft"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "assessment_sessions",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("assessment_id", sa.String(36), nullable=False),
        sa.Column("learner_profile_json", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="pending"
        ),
        sa.Column("code_session_id", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_assessment_sessions_assessment_id",
        "assessment_sessions",
        ["assessment_id"],
    )


def downgrade() -> None:
    """Roll back the migration: Drop assessments and assessment_sessions tables."""

    op.drop_index(
        "ix_assessment_sessions_assessment_id",
        table_name="assessment_sessions",
    )
    op.drop_table("assessment_sessions")
    op.drop_table("assessments")
