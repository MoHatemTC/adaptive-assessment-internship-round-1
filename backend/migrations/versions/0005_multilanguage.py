"""Widen code_challenges.language CHECK for multi-language support.

Revision ID: 0005_multilanguage
Revises: 0004_constraints_audit
Create Date: 2026-06-10
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005_multilanguage"
down_revision: Union[str, None] = "0004_constraints_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SUPPORTED_LANGUAGES = (
    "python",
    "javascript",
    "typescript",
    "java",
    "go",
    "csharp",
    "ruby",
    "rust",
    "cpp",
)


def upgrade() -> None:
    op.drop_constraint("ck_code_challenges_language", "code_challenges", type_="check")
    allowed = ", ".join(f"'{lang}'" for lang in _SUPPORTED_LANGUAGES)
    op.create_check_constraint(
        "ck_code_challenges_language",
        "code_challenges",
        f"language IN ({allowed})",
    )


def downgrade() -> None:
    op.drop_constraint("ck_code_challenges_language", "code_challenges", type_="check")
    op.create_check_constraint(
        "ck_code_challenges_language",
        "code_challenges",
        "language = 'python'",
    )
