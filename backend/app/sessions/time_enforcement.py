"""Server-side session and question time limits."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.admin.models import Assessment
from app.sessions.models import AssessmentSession
from app.shared.blueprint_utils import session_time_limit_seconds


def _parse_profile(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def apply_session_deadline(
    session: AssessmentSession,
    blueprint: dict[str, Any],
) -> None:
    """Copy blueprint session limit onto the learner profile for enforcement."""
    limit = session_time_limit_seconds(blueprint)
    if limit is None or limit <= 0:
        return
    profile = _parse_profile(session.learner_profile_json)
    limits = profile.get("_session_limits")
    if not isinstance(limits, dict):
        limits = {}
    started = session.started_at or datetime.now(timezone.utc)
    limits["session_deadline_at"] = (started + timedelta(seconds=limit)).isoformat()
    limits["session_time_limit_seconds"] = limit
    profile["_session_limits"] = limits
    session.learner_profile_json = json.dumps(profile)


def assert_within_session_time(session: AssessmentSession) -> None:
    """Raise HTTP 409 when the sitting deadline has passed."""
    profile = _parse_profile(session.learner_profile_json)
    limits = profile.get("_session_limits")
    if not isinstance(limits, dict):
        return
    raw_deadline = limits.get("session_deadline_at")
    if not raw_deadline:
        return
    try:
        deadline = datetime.fromisoformat(str(raw_deadline))
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
    except ValueError:
        return
    if datetime.now(timezone.utc) > deadline:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assessment session time limit has expired",
        )


async def load_blueprint_for_session(
    db: AsyncSession,
    session: AssessmentSession,
) -> dict[str, Any]:
    """Return parsed blueprint JSON for a session's assessment."""
    assessment = await db.get(Assessment, session.assessment_id)
    if assessment is None:
        return {}
    try:
        data = json.loads(assessment.blueprint_json or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


__all__ = [
    "apply_session_deadline",
    "assert_within_session_time",
    "load_blueprint_for_session",
]
