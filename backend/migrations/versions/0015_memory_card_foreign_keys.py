"""Link per-tool memory detail tables to platform memory_cards (WP-3).

Revision ID: 0015_memory_card_foreign_keys
Revises: 0014_proctoring_status_column
Create Date: 2026-06-27

Adds deferred FK constraints so extension tables (code_memory_cards,
voice_memory_cards) reference the canonical memory_cards row they extend.
Does not drop extension tables — audit confirms they store tool-specific
fields not present on memory_cards.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_memory_card_foreign_keys"
down_revision: Union[str, None] = "0014_proctoring_status_column"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _fk_names(conn: sa.Connection, table: str) -> set[str]:
    return {fk["name"] for fk in sa.inspect(conn).get_foreign_keys(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "code_memory_cards" in tables and "memory_cards" in tables:
        existing = _fk_names(bind, "code_memory_cards")
        if "fk_code_memory_cards_memory_card_id" not in existing:
            op.create_foreign_key(
                "fk_code_memory_cards_memory_card_id",
                "code_memory_cards",
                "memory_cards",
                ["memory_card_id"],
                ["id"],
                ondelete="CASCADE",
            )

    if "voice_memory_cards" in tables:
        if "memory_cards" in tables:
            existing = _fk_names(bind, "voice_memory_cards")
            if "fk_voice_memory_cards_memory_card_id" not in existing:
                op.create_foreign_key(
                    "fk_voice_memory_cards_memory_card_id",
                    "voice_memory_cards",
                    "memory_cards",
                    ["memory_card_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
        if "voice_sessions" in tables:
            existing = _fk_names(bind, "voice_memory_cards")
            if "fk_voice_memory_cards_voice_session_id" not in existing:
                op.create_foreign_key(
                    "fk_voice_memory_cards_voice_session_id",
                    "voice_memory_cards",
                    "voice_sessions",
                    ["voice_session_id"],
                    ["id"],
                    ondelete="CASCADE",
                )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "voice_memory_cards" in tables:
        existing = _fk_names(bind, "voice_memory_cards")
        if "fk_voice_memory_cards_voice_session_id" in existing:
            op.drop_constraint(
                "fk_voice_memory_cards_voice_session_id",
                "voice_memory_cards",
                type_="foreignkey",
            )
        if "fk_voice_memory_cards_memory_card_id" in existing:
            op.drop_constraint(
                "fk_voice_memory_cards_memory_card_id",
                "voice_memory_cards",
                type_="foreignkey",
            )

    if "code_memory_cards" in tables:
        existing = _fk_names(bind, "code_memory_cards")
        if "fk_code_memory_cards_memory_card_id" in existing:
            op.drop_constraint(
                "fk_code_memory_cards_memory_card_id",
                "code_memory_cards",
                type_="foreignkey",
            )
