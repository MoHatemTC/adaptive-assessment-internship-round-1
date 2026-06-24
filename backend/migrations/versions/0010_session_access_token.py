"""Add learner session access token columns."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0010_session_access_token"
down_revision = "0009_voice_memory_cards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {col["name"] for col in inspect(bind).get_columns("assessment_sessions")}

    if "token_hash" not in columns:
        op.add_column(
            "assessment_sessions",
            sa.Column("token_hash", sa.String(64), nullable=True),
        )
    if "expires_at" not in columns:
        op.add_column(
            "assessment_sessions",
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        )

    indexes = {idx["name"] for idx in inspect(bind).get_indexes("assessment_sessions")}
    if "ix_assessment_sessions_token_hash" not in indexes:
        op.create_index(
            "ix_assessment_sessions_token_hash",
            "assessment_sessions",
            ["token_hash"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {idx["name"] for idx in inspect(bind).get_indexes("assessment_sessions")}
    if "ix_assessment_sessions_token_hash" in indexes:
        op.drop_index(
            "ix_assessment_sessions_token_hash",
            table_name="assessment_sessions",
        )

    columns = {col["name"] for col in inspect(bind).get_columns("assessment_sessions")}
    if "expires_at" in columns:
        op.drop_column("assessment_sessions", "expires_at")
    if "token_hash" in columns:
        op.drop_column("assessment_sessions", "token_hash")
