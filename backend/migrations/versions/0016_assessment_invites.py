"""Placeholder: assessment invites migration (already applied on Supabase).

Revision ID: 0016_assessment_invites
Revises: 0015_memory_card_foreign_keys
Create Date: 2026-06-30

This revision exists only to satisfy Alembic's dependency chain — the schema
change was applied directly on Supabase and the file was not committed to the
codebase. The upgrade/downgrade are no-ops.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_assessment_invites"
down_revision: Union[str, None] = "0015_memory_card_foreign_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
