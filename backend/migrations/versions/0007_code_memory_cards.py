"""Code memory cards for adaptive evaluation loop.

Revision ID: 0007_code_memory_cards
Revises: 0006_platform_sessions
Create Date: 2026-06-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_code_memory_cards"
down_revision: Union[str, None] = "0006_platform_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "code_memory_cards",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("platform_session_id", sa.Text(), nullable=True),
        sa.Column("code_session_id", sa.String(length=64), nullable=False),
        sa.Column("challenge_id", sa.Integer(), sa.ForeignKey("code_challenges.id"), nullable=False),
        sa.Column("problem_type", sa.String(length=64), nullable=False),
        sa.Column("difficulty", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("pass_rate", sa.Float(), nullable=False),
        sa.Column("efficiency", sa.Float(), nullable=False),
        sa.Column("rubric_score", sa.Float(), nullable=False),
        sa.Column("dimension_signals_json", sa.Text(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("test_results_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_code_memory_cards_code_session_id",
        "code_memory_cards",
        ["code_session_id"],
    )
    op.create_index(
        "ix_code_memory_cards_platform_session_id",
        "code_memory_cards",
        ["platform_session_id"],
    )

    op.add_column(
        "code_assessment_sessions",
        sa.Column("analysis_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("code_assessment_sessions", "analysis_json")
    op.drop_index("ix_code_memory_cards_platform_session_id", table_name="code_memory_cards")
    op.drop_index("ix_code_memory_cards_code_session_id", table_name="code_memory_cards")
    op.drop_table("code_memory_cards")
