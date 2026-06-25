"""Rebuild diagram feature around inline SVG questions.

Revision ID: 0012_rebuild_diagram_svg_unified_pattern
Revises: 0011_mcq_adaptive_columns
Create Date: 2026-06-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_rebuild_diagram_svg_unified_pattern"
down_revision: Union[str, None] = "0011_mcq_adaptive_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_diagram_dimension = sa.Enum(
    "thinking",
    "soft",
    "work",
    "digital_ai",
    "growth",
    name="diagram_skill_dimension",
)


def upgrade() -> None:
    op.drop_index("ix_diagram_answers_session_id", table_name="diagram_answers")
    op.drop_table("diagram_answers")
    op.drop_table("diagram_questions")
    op.execute("DROP TYPE IF EXISTS skilldimension")
    op.execute("DROP TYPE IF EXISTS difficulty")

    _diagram_dimension.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "diagram_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("svg_content", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("correct_label", sa.String(length=255), nullable=False),
        sa.Column("rubric", sa.Text(), nullable=False),
        sa.Column(
            "difficulty",
            sa.String(length=50),
            server_default="easy",
            nullable=False,
        ),
        sa.Column("dimension", _diagram_dimension, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_table(
        "diagram_responses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("learner_id", sa.String(length=255), nullable=True),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column(
            "score",
            sa.Float(),
            nullable=True,
            comment="1.0 = correct, 0.0 = wrong. Never exposed to learner.",
        ),
        sa.Column(
            "grading_feedback",
            sa.Text(),
            nullable=True,
            comment="Server-side only. Never exposed to learner.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["question_id"], ["diagram_questions.id"]),
    )
    op.create_index(
        "ix_diagram_responses_session_id",
        "diagram_responses",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_diagram_responses_session_id", table_name="diagram_responses")
    op.drop_table("diagram_responses")
    op.drop_table("diagram_questions")
    _diagram_dimension.drop(op.get_bind(), checkfirst=True)

    difficulty_enum = sa.Enum("easy", "medium", "hard", name="difficulty")
    skill_dimension_enum = sa.Enum(
        "thinking", "soft", "work", "digital_ai", "growth", name="skilldimension"
    )
    difficulty_enum.create(op.get_bind(), checkfirst=True)
    skill_dimension_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "diagram_questions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("image_url", sa.String(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("rubric", sa.Text(), nullable=False),
        sa.Column("difficulty", difficulty_enum, nullable=False),
        sa.Column("dimension", skill_dimension_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "diagram_answers",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("question_id", sa.UUID(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("grading_feedback", sa.Text(), nullable=True),
        sa.Column("graded_at", sa.DateTime(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["diagram_questions.id"]),
    )
    op.create_index("ix_diagram_answers_session_id", "diagram_answers", ["session_id"])
