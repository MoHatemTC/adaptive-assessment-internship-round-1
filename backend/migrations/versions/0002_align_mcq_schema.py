"""align mcq schema with unified platform schema

Revision ID: 0002_align_mcq_schema
Revises: 0001_mcq
Create Date: 2026-06-15
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_align_mcq_schema"
down_revision = "0001_mcq"
branch_labels = None
depends_on = None


def upgrade():
    """
    Align MCQ-owned tables with the unified schema.

    Rules:
    - mcq_responses stores learner submissions only.
    - No score, correctness, or learner_id on mcq_responses.
    - session_id is String(36), FK deferred until assessment_sessions exists.
    - question_index is required.
    - difficulty values are beginner/intermediate/advanced.
    - dimension is stored on mcq_questions.
    """

    op.add_column(
        "mcq_questions",
        sa.Column("dimension", sa.String(length=20), nullable=True),
    )

    op.execute(
        """
        UPDATE mcq_questions
        SET difficulty = CASE
            WHEN difficulty = 'easy' THEN 'beginner'
            WHEN difficulty = 'medium' THEN 'intermediate'
            WHEN difficulty = 'hard' THEN 'advanced'
            ELSE difficulty
        END
        """
    )

    op.alter_column(
        "mcq_questions",
        "difficulty",
        existing_type=sa.String(length=50),
        type_=sa.String(length=20),
        existing_nullable=False,
        server_default="beginner",
    )

    op.add_column(
        "mcq_responses",
        sa.Column("question_index", sa.Integer(), nullable=False, server_default="0"),
    )

    op.alter_column(
        "mcq_responses",
        "question_index",
        server_default=None,
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    op.alter_column(
        "mcq_responses",
        "session_id",
        existing_type=sa.String(),
        type_=sa.String(length=36),
        existing_nullable=False,
    )

    op.drop_column("mcq_responses", "learner_id")
    op.drop_column("mcq_responses", "is_correct")
    op.drop_column("mcq_responses", "score")


def downgrade():
    """
    Roll back to the original Sprint 1 MCQ schema.
    """

    op.add_column(
        "mcq_responses",
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "mcq_responses",
        sa.Column("is_correct", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "mcq_responses",
        sa.Column("learner_id", sa.String(length=255), nullable=True),
    )

    op.alter_column(
        "mcq_responses",
        "session_id",
        existing_type=sa.String(length=36),
        type_=sa.String(),
        existing_nullable=False,
    )

    op.drop_column("mcq_responses", "question_index")

    op.execute(
        """
        UPDATE mcq_questions
        SET difficulty = CASE
            WHEN difficulty = 'beginner' THEN 'easy'
            WHEN difficulty = 'intermediate' THEN 'medium'
            WHEN difficulty = 'advanced' THEN 'hard'
            ELSE difficulty
        END
        """
    )

    op.alter_column(
        "mcq_questions",
        "difficulty",
        existing_type=sa.String(length=20),
        type_=sa.String(length=50),
        existing_nullable=False,
        server_default="easy",
    )

    op.drop_column("mcq_questions", "dimension")
