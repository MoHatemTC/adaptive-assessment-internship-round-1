"""Add adaptive/grading columns to mcq_questions and mcq_responses.

Adds the columns the shared adaptation agent's ``_fetch_mcq_answers`` reads:
``mcq_responses.score`` (nullable float), ``mcq_responses.grading_feedback``,
and ``mcq_questions.dimension`` (skill dimension enum, reached through the
``MCQResponse.question`` relationship). Also tightens
``mcq_responses.session_id`` to ``String(36)`` per the platform session-id law.

Revision ID: 0011_mcq_adaptive_columns
Revises: 0010_session_access_token
Create Date: 2026-06-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_mcq_adaptive_columns"
down_revision: Union[str, None] = "0010_session_access_token"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Distinct enum type name so it never collides with the diagram feature's
# own ``skilldimension`` Postgres enum.
_mcq_dimension = sa.Enum(
    "thinking",
    "soft",
    "work",
    "digital_ai",
    "growth",
    name="mcq_skill_dimension",
)


def upgrade() -> None:
    # mcq_questions.dimension — nullable so existing questions are preserved.
    _mcq_dimension.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "mcq_questions",
        sa.Column(
            "dimension",
            _mcq_dimension,
            nullable=True,
            comment=(
                "Skill dimension this question targets "
                "(thinking/soft/work/digital_ai/growth)."
            ),
        ),
    )

    # mcq_responses.grading_feedback — internal, nullable, never shown to learner.
    op.add_column(
        "mcq_responses",
        sa.Column(
            "grading_feedback",
            sa.Text(),
            nullable=True,
            comment="Internal grading feedback. Never exposed to learner.",
        ),
    )

    # mcq_responses.score — int (non-null, default 0) -> float (nullable). NULL now
    # means "not yet graded" so the adaptation agent can filter on score IS NOT NULL.
    op.alter_column(
        "mcq_responses",
        "score",
        existing_type=sa.Integer(),
        type_=sa.Float(),
        existing_nullable=False,
        nullable=True,
        postgresql_using="score::double precision",
        comment="Silent grading score 0.0-1.0. Never exposed to learner.",
    )

    # mcq_responses.session_id — varchar -> varchar(36) to match the platform law.
    op.alter_column(
        "mcq_responses",
        "session_id",
        existing_type=sa.String(),
        type_=sa.String(length=36),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "mcq_responses",
        "session_id",
        existing_type=sa.String(length=36),
        type_=sa.String(),
        existing_nullable=False,
    )

    # Restore NOT NULL int score; coalesce any ungraded NULLs back to 0.
    op.alter_column(
        "mcq_responses",
        "score",
        existing_type=sa.Float(),
        type_=sa.Integer(),
        existing_nullable=True,
        nullable=False,
        postgresql_using="coalesce(score, 0)::integer",
        comment=None,
    )

    op.drop_column("mcq_responses", "grading_feedback")

    op.drop_column("mcq_questions", "dimension")
    _mcq_dimension.drop(op.get_bind(), checkfirst=True)
