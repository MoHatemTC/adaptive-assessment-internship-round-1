"""Add cv_required to assessments and id_card_image_b64 to assessment_sessions.

Revision ID: 0018_cv_required_id_card
Revises: 0017_session_judge_review
Create Date: 2026-07-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0018_cv_required_id_card"
down_revision: Union[str, None] = "0017_session_judge_review"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    assessment_columns = {
        col["name"] for col in inspect(bind).get_columns("assessments")
    }
    if "cv_required" not in assessment_columns:
        op.add_column(
            "assessments",
            sa.Column(
                "cv_required",
                sa.Boolean(),
                nullable=False,
                server_default="false",
                comment="Admin-controlled: whether CV upload is required for learners",
            ),
        )

    session_columns = {
        col["name"] for col in inspect(bind).get_columns("assessment_sessions")
    }
    if "id_card_image_b64" not in session_columns:
        op.add_column(
            "assessment_sessions",
            sa.Column(
                "id_card_image_b64",
                sa.Text(),
                nullable=True,
                comment=(
                    "Base64-encoded national ID card image uploaded at intake "
                    "for identity verification"
                ),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()

    session_columns = {
        col["name"] for col in inspect(bind).get_columns("assessment_sessions")
    }
    if "id_card_image_b64" in session_columns:
        op.drop_column("assessment_sessions", "id_card_image_b64")

    assessment_columns = {
        col["name"] for col in inspect(bind).get_columns("assessments")
    }
    if "cv_required" in assessment_columns:
        op.drop_column("assessments", "cv_required")
