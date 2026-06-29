"""Server-side proctoring gates for tool APIs and the examiner.

Karim wires :func:`ensure_tool_session_allowed` at the top of each tool service
method that accepts a ``session_id``. Abutaleb reads
:func:`get_integrity_snapshot_for_admin` for the results UI.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.proctoring.models import ProctoringEvent
from app.proctoring.service import compute_verification_status, resolve_policy
from app.sessions.models import AssessmentSession
from app.sessions.time_enforcement import assert_within_session_time
from app.shared.schemas.proctoring import ProctoringPolicy, SessionIntegritySnapshot


_ACTIVE_STATUSES = frozenset({"active"})
_TERMINAL_STATUSES = frozenset({"completed", "expired"})


def _parse_profile(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def _load_events(db: AsyncSession, session_id: str) -> list[ProctoringEvent]:
    result = await db.exec(
        select(ProctoringEvent)
        .where(ProctoringEvent.session_id == session_id)
        .order_by(ProctoringEvent.created_at)
    )
    return list(result.all())


def _has_identity_verified(events: list[ProctoringEvent]) -> bool:
    return any(event.event_type == "identity_verified" for event in events)


async def assert_session_ready_for_tools(
    db: AsyncSession,
    session: AssessmentSession,
    *,
    policy: ProctoringPolicy | None = None,
) -> ProctoringPolicy:
    """Raise HTTP 403/409 when a learner session may not use tool endpoints."""
    resolved = policy or await resolve_policy(db, session)
    profile = _parse_profile(session.learner_profile_json)

    if session.status in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assessment session is no longer active",
        )
    if session.status == "flagged":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session flagged for integrity review — assessment tools are locked",
        )
    if session.status not in _ACTIVE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session must be started before using assessment tools",
        )
    assert_within_session_time(session)
    if not profile.get("consent_given"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Proctoring consent is required before using assessment tools",
        )

    events = await _load_events(db, session.id)
    if resolved.require_camera and not _has_identity_verified(events):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Identity verification is required before using assessment tools",
        )

    verification = compute_verification_status(
        session_status=session.status,
        events=events,
        policy=resolved,
    )
    if verification == "identity_failed":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Identity verification failed for this session",
        )

    return resolved


async def ensure_tool_session_allowed(
    db: AsyncSession,
    session_id: str,
) -> AssessmentSession:
    """Load a session by id and enforce proctoring readiness (tool APIs without bearer)."""
    session = await db.get(AssessmentSession, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="assessment session not found",
        )
    await assert_session_ready_for_tools(db, session)
    return session


async def get_integrity_snapshot_for_admin(
    db: AsyncSession,
    session_id: str,
) -> SessionIntegritySnapshot:
    """Compact integrity summary for Abutaleb's admin results panel."""
    session = await db.get(AssessmentSession, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="assessment session not found",
        )
    policy = await resolve_policy(db, session)
    events = await _load_events(db, session_id)
    high_count = sum(1 for event in events if event.severity == "high")
    verification = compute_verification_status(
        session_status=session.status,
        events=events,
        policy=policy,
    )
    return SessionIntegritySnapshot(
        verification_status=verification,
        high_severity_count=high_count,
        threshold=policy.high_severity_threshold,
        identity_verified=_has_identity_verified(events),
    )


__all__ = [
    "assert_session_ready_for_tools",
    "ensure_tool_session_allowed",
    "get_integrity_snapshot_for_admin",
]
