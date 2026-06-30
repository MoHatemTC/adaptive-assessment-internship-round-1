"""Migration: assessment invites and identity reference storage.

Revision ID: 0016_assessment_invites
Revises: 0015_memory_card_foreign_keys
Create Date: 2026-06-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0016_assessment_invites"
down_revision: Union[str, None] = "0015_memory_card_foreign_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "assessment_invites" not in tables:
        op.create_table(
            "assessment_invites",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("assessment_id", sa.String(length=36), nullable=False),
            sa.Column("token", sa.String(length=64), nullable=False),
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="active",
            ),
            sa.Column("label", sa.Text(), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    invite_indexes = {
        idx["name"] for idx in inspect(bind).get_indexes("assessment_invites")
    }
    if "ix_assessment_invites_assessment_id" not in invite_indexes:
        op.create_index(
            "ix_assessment_invites_assessment_id",
            "assessment_invites",
            ["assessment_id"],
        )
    if "ix_assessment_invites_token" not in invite_indexes:
        op.create_index(
            "ix_assessment_invites_token",
            "assessment_invites",
            ["token"],
            unique=True,
        )

    session_columns = {
        col["name"] for col in inspector.get_columns("assessment_sessions")
    }
    if "identity_reference_b64" not in session_columns:
        op.add_column(
            "assessment_sessions",
            sa.Column("identity_reference_b64", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    session_columns = {
        col["name"] for col in inspector.get_columns("assessment_sessions")
    }
    if "identity_reference_b64" in session_columns:
        op.drop_column("assessment_sessions", "identity_reference_b64")

    tables = set(inspector.get_table_names())
    if "assessment_invites" in tables:
        invite_indexes = {
            idx["name"] for idx in inspector.get_indexes("assessment_invites")
        }
        if "ix_assessment_invites_token" in invite_indexes:
            op.drop_index(
                "ix_assessment_invites_token",
                table_name="assessment_invites",
            )
        if "ix_assessment_invites_assessment_id" in invite_indexes:
            op.drop_index(
                "ix_assessment_invites_assessment_id",
                table_name="assessment_invites",
            )
        op.drop_table("assessment_invites")
