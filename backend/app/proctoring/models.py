"""SQLAlchemy 2.0 ORM model for proctoring events."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, String, Text, func

from app.core.database import Base, Mapped, mapped_column


class ProctoringEvent(Base):
    """An integrity event recorded in parallel during any tool session.

    Events are written by the frontend proctoring layer and stored for admin
    review. A session can be flagged automatically when high-severity events
    exceed a configurable threshold.

    Attributes:
        id: Surrogate primary key.
        session_id: Owning assessment session UUID.
        event_type: Category of integrity event.
        severity: Risk level of the event.
        metadata_json: Optional JSON with extra context (browser info, etc.).
        client_timestamp: Browser-reported event time, or ``None`` if unavailable.
        created_at: Server-set timestamp of row insertion.
    """

    __tablename__ = "proctoring_events"
    __table_args__ = (
        Index("ix_proctoring_events_session_id", "session_id"),
        Index("ix_proctoring_events_event_type", "event_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # FK deferred until assessment_sessions table exists
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # "tab_switch" / "copy_paste" / "screenshot" / "ai_usage" / "identity_fail"
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    # "low" / "medium" / "high"
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSON: extra context
    client_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
