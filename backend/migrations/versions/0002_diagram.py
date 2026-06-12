"""create diagram and diagram question tables

Revision ID: 0002_diagram
Revises: "0001_mcq"
Create Date: 2026-06-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_diagram"
down_revision = "0001_mcq"
branch_labels = None
depends_on = None


def upgrade():
    """
    Apply the migration:
    Create diagram tables, question tables, and indexes.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "diagrams" not in table_names:
        op.create_table(
            "diagrams",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("model_name", sa.String(length=255), nullable=False, server_default="gpt-4o"),
            sa.Column("image_url", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        existing_columns = {
            column["name"]
            for column in inspector.get_columns("diagrams")
        }
        if "model_name" not in existing_columns:
            op.add_column(
                "diagrams",
                sa.Column(
                    "model_name",
                    sa.String(length=255),
                    nullable=False,
                    server_default="gpt-4o",
                ),
            )

    existing_indexes = {
        index["name"]
        for index in inspector.get_indexes("diagrams")
    }
    if "ix_diagrams_user_id" not in existing_indexes:
        op.create_index("ix_diagrams_user_id", "diagrams", ["user_id"], unique=False)

    if "diagram_questions" not in table_names:
        op.create_table(
            "diagram_questions",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("prompt_text", sa.Text(), nullable=False),
            sa.Column("difficulty", sa.String(length=50), nullable=False, server_default="easy"),
            sa.Column("correct_answer", sa.Text(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    if "diagram_options" not in table_names:
        op.create_table(
            "diagram_options",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("question_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("diagram_questions.id"), nullable=False),
            sa.Column("label", sa.String(length=50), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if "diagram_responses" not in table_names:
        op.create_table(
            "diagram_responses",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("question_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("diagram_questions.id"), nullable=False),
            sa.Column("learner_id", sa.String(length=255), nullable=True),
            sa.Column("selected_option", sa.String(length=50), nullable=False),
            sa.Column("is_correct", sa.Boolean(), nullable=False),
            sa.Column("score", sa.Integer(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade():
    """
    Roll back the migration:
    Drop diagram tables and indexes.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "diagram_responses" in table_names:
        op.drop_table("diagram_responses")

    if "diagram_options" in table_names:
        op.drop_table("diagram_options")

    if "diagram_questions" in table_names:
        op.drop_table("diagram_questions")

    if "diagrams" not in table_names:
        return

    existing_indexes = {
        index["name"]
        for index in inspector.get_indexes("diagrams")
    }
    if "ix_diagrams_user_id" in existing_indexes:
        op.drop_index("ix_diagrams_user_id", table_name="diagrams")

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("diagrams")
    }
    if "model_name" in existing_columns:
        op.drop_column("diagrams", "model_name")
