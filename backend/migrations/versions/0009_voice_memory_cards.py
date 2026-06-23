"""Create voice_memory_cards table.

Revision ID: 0009_voice_memory_cards
Revises: 0008_voice_adaptive_columns
Create Date: 2026-06-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_voice_memory_cards"
down_revision = "0008_voice_adaptive_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the migration: create the voice_memory_cards table."""

    op.create_table(
        "voice_memory_cards",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("voice_session_id", sa.Integer(), nullable=False),
        sa.Column("memory_card_id", sa.Integer(), nullable=True),
        sa.Column("competency", sa.Text(), nullable=False),
        sa.Column(
            "rubric_scores_json", sa.Text(), nullable=False, server_default="{}"
        ),
        sa.Column(
            "communication_signals_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_voice_memory_cards_voice_session_id",
        "voice_memory_cards",
        ["voice_session_id"],
    )


def downgrade() -> None:
    """Roll back the migration: drop the voice_memory_cards table."""

    op.drop_index(
        "ix_voice_memory_cards_voice_session_id",
        table_name="voice_memory_cards",
    )
    op.drop_table("voice_memory_cards")
