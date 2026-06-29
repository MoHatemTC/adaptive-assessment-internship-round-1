"""Resolve blueprint limits for an MCQ session."""

from __future__ import annotations

import json
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.admin.models import Assessment
from app.sessions.models import AssessmentSession
from app.shared.blueprint_utils import tool_question_count


def _parse_profile(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def mcq_blueprint_context(
    db: AsyncSession,
    session_id: str,
) -> tuple[AssessmentSession, dict[str, Any], int, dict[str, Any]]:
    """Load session, blueprint, question budget, and learner profile."""
    session = await db.get(AssessmentSession, session_id)
    if session is None:
        raise ValueError("assessment session not found")

    assessment = await db.get(Assessment, session.assessment_id)
    blueprint: dict[str, Any] = {}
    if assessment is not None:
        try:
            blueprint = json.loads(assessment.blueprint_json or "{}")
        except json.JSONDecodeError:
            blueprint = {}
        if not isinstance(blueprint, dict):
            blueprint = {}

    total = tool_question_count(blueprint, "mcq", legacy_keys=("mcq",)) or 5
    profile = _parse_profile(session.learner_profile_json)
    return session, blueprint, max(1, total), profile


__all__ = ["mcq_blueprint_context"]
