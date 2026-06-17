"""Create code_memory_cards detail table.

Revision ID: 0002_code_memory_cards
Revises: 0001_code
Create Date: 2026-06-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_code_memory_cards"
down_revision: Union[str, None] = "0001_code"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "code_memory_cards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("question_index", sa.Integer(), nullable=False),
        sa.Column("submission_id", sa.Integer(), nullable=False),
        sa.Column("memory_card_id", sa.Integer(), nullable=False),
        sa.Column("sandbox_score", sa.Float(), nullable=False),
        sa.Column("approach_feedback", sa.Text(), nullable=False),
        sa.Column("efficiency_feedback", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["submission_id"], ["code_submissions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_code_memory_cards_session_id", "code_memory_cards", ["session_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_code_memory_cards_session_id", table_name="code_memory_cards")
    op.drop_table("code_memory_cards")
