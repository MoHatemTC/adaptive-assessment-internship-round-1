"""Create grading and memory tables.

Revision ID: 0004_grading
Revises: 0003_platform_sessions
Create Date: 2026-06-16
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_grading"
down_revision = "0003_platform_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the migration: Create grade_results, memory_cards, skill_dimension_scores."""

    op.create_table(
        "grade_results",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("tool_type", sa.String(20), nullable=False),
        sa.Column("tool_session_id", sa.Integer(), nullable=False),
        sa.Column("question_index", sa.Integer(), nullable=False),
        sa.Column("rubric_scores", sa.Text(), nullable=False),
        sa.Column("llm_judge_score", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_grade_results_session_id", "grade_results", ["session_id"]
    )

    op.create_table(
        "memory_cards",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("tool_type", sa.String(20), nullable=False),
        sa.Column("question_index", sa.Integer(), nullable=False),
        sa.Column("difficulty", sa.String(20), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("dimension_signals", sa.Text(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_memory_cards_session_id", "memory_cards", ["session_id"]
    )

    op.create_table(
        "skill_dimension_scores",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("question_index", sa.Integer(), nullable=False),
        sa.Column("tool_type", sa.String(20), nullable=False),
        sa.Column("thinking", sa.SmallInteger(), nullable=True),
        sa.Column("soft", sa.SmallInteger(), nullable=True),
        sa.Column("work", sa.SmallInteger(), nullable=True),
        sa.Column("digital_ai", sa.SmallInteger(), nullable=True),
        sa.Column("growth", sa.SmallInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "thinking IS NULL OR (thinking >= 1 AND thinking <= 10)",
            name="ck_sds_thinking",
        ),
        sa.CheckConstraint(
            "soft IS NULL OR (soft >= 1 AND soft <= 10)",
            name="ck_sds_soft",
        ),
        sa.CheckConstraint(
            "work IS NULL OR (work >= 1 AND work <= 10)",
            name="ck_sds_work",
        ),
        sa.CheckConstraint(
            "digital_ai IS NULL OR (digital_ai >= 1 AND digital_ai <= 10)",
            name="ck_sds_digital_ai",
        ),
        sa.CheckConstraint(
            "growth IS NULL OR (growth >= 1 AND growth <= 10)",
            name="ck_sds_growth",
        ),
    )
    op.create_index(
        "ix_skill_dimension_scores_session_id",
        "skill_dimension_scores",
        ["session_id"],
    )


def downgrade() -> None:
    """Roll back the migration: Drop grading and memory tables."""

    op.drop_index(
        "ix_skill_dimension_scores_session_id",
        table_name="skill_dimension_scores",
    )
    op.drop_table("skill_dimension_scores")
    op.drop_index("ix_memory_cards_session_id", table_name="memory_cards")
    op.drop_table("memory_cards")
    op.drop_index("ix_grade_results_session_id", table_name="grade_results")
    op.drop_table("grade_results")
