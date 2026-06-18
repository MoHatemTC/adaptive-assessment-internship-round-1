"""Add structured evidence fields to code memory cards.

Revision ID: 0006_code_memory_card_evidence
Revises: 0002_code_memory_cards
Create Date: 2026-06-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_code_memory_card_evidence"
down_revision: Union[str, None] = "0002_code_memory_cards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "code_memory_cards",
        sa.Column(
            "overall_rubric_score",
            sa.Float(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "code_memory_cards",
        sa.Column(
            "test_results",
            sa.Text(),
            server_default="[]",
            nullable=False,
        ),
    )
    op.alter_column("code_memory_cards", "overall_rubric_score", server_default=None)
    op.alter_column("code_memory_cards", "test_results", server_default=None)


def downgrade() -> None:
    op.drop_column("code_memory_cards", "test_results")
    op.drop_column("code_memory_cards", "overall_rubric_score")
