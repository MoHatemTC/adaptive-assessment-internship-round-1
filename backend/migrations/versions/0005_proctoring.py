"""Create proctoring events table.

Revision ID: 0005_proctoring
Revises: 0004_grading
Create Date: 2026-06-16
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_proctoring"
down_revision = "0004_grading"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply the migration: Create proctoring_events table."""

    op.create_table(
        "proctoring_events",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("client_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_proctoring_events_session_id", "proctoring_events", ["session_id"]
    )
    op.create_index(
        "ix_proctoring_events_event_type", "proctoring_events", ["event_type"]
    )


def downgrade() -> None:
    """Roll back the migration: Drop proctoring_events table."""

    op.drop_index(
        "ix_proctoring_events_event_type", table_name="proctoring_events"
    )
    op.drop_index(
        "ix_proctoring_events_session_id", table_name="proctoring_events"
    )
    op.drop_table("proctoring_events")
