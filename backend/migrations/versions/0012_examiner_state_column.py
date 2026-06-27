"""Add examiner_state_json to assessment_sessions.

Revision ID: 0012_examiner_state_column
Revises: 0011_mcq_adaptive_columns
Create Date: 2026-06-24

This revision was applied directly to the team Supabase instance before the
migration file was merged. Restored here so Alembic history matches production.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_examiner_state_column"
down_revision: Union[str, None] = "0011_mcq_adaptive_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("assessment_sessions")}
    if "examiner_state_json" not in columns:
        op.add_column(
            "assessment_sessions",
            sa.Column("examiner_state_json", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("assessment_sessions")}
    if "examiner_state_json" in columns:
        op.drop_column("assessment_sessions", "examiner_state_json")
