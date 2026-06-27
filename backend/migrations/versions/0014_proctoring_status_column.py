"""Add proctoring_status to assessment_sessions.

Revision ID: 0014_proctoring_status_column
Revises: 0013_diagram_svg_rebuild
Create Date: 2026-06-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_proctoring_status_column"
down_revision: Union[str, None] = "0013_diagram_svg_rebuild"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("assessment_sessions")}
    if "proctoring_status" not in columns:
        op.add_column(
            "assessment_sessions",
            sa.Column(
                "proctoring_status",
                sa.String(length=20),
                nullable=False,
                server_default="not_started",
            ),
        )


def downgrade() -> None:
    op.drop_column("assessment_sessions", "proctoring_status")
