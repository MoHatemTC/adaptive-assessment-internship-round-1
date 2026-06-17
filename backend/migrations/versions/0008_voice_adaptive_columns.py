"""Add adaptive question columns to voice_sessions.

Revision ID: 0008_voice_adaptive_columns
Revises: 0002_code_memory_cards
Create Date: 2026-06-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_voice_adaptive_columns"
down_revision: Union[str, None] = "0002_code_memory_cards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable so existing voice_sessions rows are preserved.
    op.add_column(
        "voice_sessions",
        sa.Column("question_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "voice_sessions",
        sa.Column("question_index", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("voice_sessions", "question_index")
    op.drop_column("voice_sessions", "question_text")
