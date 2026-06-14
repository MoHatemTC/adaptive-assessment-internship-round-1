"""Session audit logging for candidate lifecycle events."""

from __future__ import annotations

import json
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.code.models import SessionAuditEvent


async def record_session_audit(
    db: AsyncSession,
    *,
    session_id: str,
    event_type: str,
    actor: str = "candidate",
    metadata: dict[str, Any] | None = None,
) -> SessionAuditEvent:
    """Persist an immutable audit event for compliance and support review."""
    row = SessionAuditEvent(
        session_id=session_id,
        event_type=event_type,
        actor=actor,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    db.add(row)
    return row
