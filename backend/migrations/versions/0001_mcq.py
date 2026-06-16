"""create mcq tables

Revision ID: 0001_mcq
Revises: 
Create Date: 2026-06-09
"""

from alembic import op
import sqlalchemy as sa

 
revision = "0001_mcq"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """
    Apply the migration:
    Create MCQ tables.
    """

    op.create_table(
        "mcq_questions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("correct_option", sa.String(length=10), nullable=False),
        sa.Column("difficulty", sa.String(length=50), nullable=False, server_default="easy"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "mcq_options",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("mcq_questions.id"), nullable=False),
        sa.Column("label", sa.String(length=10), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
    )

    op.create_table(
        "mcq_responses",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("mcq_questions.id"), nullable=False),
        # FK to assessment_sessions.id — constraint added via a later migration
        # once the sessions feature is merged. Indexed so responses are
        # queryable per session in the meantime.
        sa.Column("session_id", sa.String(), nullable=False, index=True),
        sa.Column("learner_id", sa.String(length=255), nullable=True),
        sa.Column("selected_option", sa.String(length=10), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    """
    Roll back the migration:
    Drop MCQ tables.
    """

    op.drop_table("mcq_responses")
    op.drop_table("mcq_options")
    op.drop_table("mcq_questions")