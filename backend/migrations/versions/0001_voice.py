"""create voice tables

Revision ID: 0001_voice
Revises: 0001_mcq
Create Date: 2026-06-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_voice"
down_revision = "0001_mcq"
branch_labels = None
depends_on = None


def upgrade():
    """
    Apply the migration:
    Create voice interview tables.
    """

    op.create_table(
        "voice_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        # links to assessment session — no FK until sessions feature merges.
        # Indexed so sessions are queryable per assessment in the meantime.
        sa.Column("session_id", sa.String(), nullable=False, index=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("time_limit_seconds", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "voice_transcripts",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "voice_session_id",
            sa.Integer(),
            sa.ForeignKey("voice_sessions.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("transcript_text", sa.Text(), nullable=False),
        sa.Column("speaker_confidence", sa.Float(), nullable=True),
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    """
    Roll back the migration:
    Drop voice interview tables.
    """

    op.drop_table("voice_transcripts")
    op.drop_table("voice_sessions")
