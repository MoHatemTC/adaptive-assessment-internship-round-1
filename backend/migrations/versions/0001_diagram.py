"""0001_diagram

Revision ID: 0001_diagram
Revises: 0001_mcq
Create Date: 2026-06-11

Creates:
  - diagram_questions  (the item: image_url, prompt, rubric, difficulty, dimension)
  - diagram_answers    (learner response per session, with grading columns)

Checks the README TODO for the diagram migration.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_diagram"
down_revision = "0005_proctoring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    difficulty_enum = postgresql.ENUM(
        "easy", "medium", "hard",
        name="difficulty",
        create_type=True,
    )
    difficulty_enum.create(op.get_bind(), checkfirst=True)

    skill_dimension_enum = postgresql.ENUM(
        "thinking", "soft", "work", "digital_ai", "growth",
        name="skilldimension",
        create_type=True,
    )
    skill_dimension_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "diagram_questions",
        sa.Column("id",         postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("image_url",  sa.String(),  nullable=False),
        sa.Column("prompt",     sa.Text(),    nullable=False),
        sa.Column("rubric",     sa.Text(),    nullable=False),
        sa.Column("difficulty", postgresql.ENUM("easy", "medium", "hard", name="difficulty", create_type=False), nullable=False),
        sa.Column("dimension",  postgresql.ENUM("thinking", "soft", "work", "digital_ai", "growth", name="skilldimension", create_type=False), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "diagram_answers",
        sa.Column("id",               postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id",       postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id",      postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("answer_text",      sa.Text(),   nullable=False),
        sa.Column("score",            sa.Float(),  nullable=True),
        sa.Column("grading_feedback", sa.Text(),   nullable=True),
        sa.Column("graded_at",        sa.DateTime(), nullable=True),
        sa.Column("submitted_at",     sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["diagram_questions.id"]),
    )
    op.create_index("ix_diagram_answers_session_id", "diagram_answers", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_diagram_answers_session_id", table_name="diagram_answers")
    op.drop_table("diagram_answers")
    op.drop_table("diagram_questions")
    op.execute("DROP TYPE IF EXISTS skilldimension")
    op.execute("DROP TYPE IF EXISTS difficulty")