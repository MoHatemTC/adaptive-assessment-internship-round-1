"""SQLAlchemy 2.0 ORM model for assessment administration."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func

from app.core.database import Base, Mapped, mapped_column


class Assessment(Base):
    """An admin-configured assessment blueprint.

    Owned by the platform layer. Every :class:`~app.sessions.models.AssessmentSession`
    references one of these rows via ``assessment_id``.

    Attributes:
        id: UUID primary key generated on insertion.
        title: Short assessment name displayed in the admin UI.
        prompt: Admin configuration prompt used by the Generator Agent.
        blueprint_json: JSON question plans, tool config, and difficulty progression.
        tool_config: JSON tool enable flags per tool type.
        status: Lifecycle state: ``"draft"`` / ``"active"`` / ``"archived"``.
        cv_required: Admin-controlled: whether CV upload is required for learners.
        created_at: Server-set timestamp of row insertion.
        updated_at: Server-set timestamp of last update.
    """

    __tablename__ = "assessments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    # Admin configuration prompt
    blueprint_json: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON: question plans, tool config, difficulty progression
    tool_config: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON: {"voice": true, "mcq": true, "diagram": true, "coding": true}
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    # "draft" / "active" / "archived"
    cv_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="Admin-controlled: whether CV upload is required for learners",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
