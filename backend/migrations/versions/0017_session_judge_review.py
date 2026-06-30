"""Add judge review storage for HITL admin approval.

Revision ID: 0017_session_judge_review
Revises: 0016_assessment_invites
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0017_session_judge_review"
down_revision: Union[str, None] = "0016_assessment_invites"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {col["name"] for col in inspect(bind).get_columns("assessment_sessions")}
    if "judge_review_json" not in columns:
        op.add_column(
            "assessment_sessions",
            sa.Column("judge_review_json", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {col["name"] for col in inspect(bind).get_columns("assessment_sessions")}
    if "judge_review_json" in columns:
        op.drop_column("assessment_sessions", "judge_review_json")
