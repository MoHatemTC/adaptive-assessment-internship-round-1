"""In-session cache for async diagram question delivery."""

from __future__ import annotations

import json
import time
from typing import Any

from app.sessions.models import AssessmentSession

_CACHE_KEY = "_diagram_cache"


def _parse_profile(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def get_diagram_cache(session: AssessmentSession) -> dict[str, Any]:
    profile = _parse_profile(session.learner_profile_json)
    cache = profile.get(_CACHE_KEY)
    return cache if isinstance(cache, dict) else {}


def _write_cache(session: AssessmentSession, cache: dict[str, Any]) -> None:
    profile = _parse_profile(session.learner_profile_json)
    profile[_CACHE_KEY] = cache
    session.learner_profile_json = json.dumps(profile)


def set_diagram_generating(
    session: AssessmentSession,
    *,
    total_questions: int,
    for_index: int,
) -> None:
    _write_cache(
        session,
        {
            "status": "generating",
            "total_questions": total_questions,
            "for_index": for_index,
            "question": None,
            "error": None,
            "started_at": time.time(),
        },
    )


def set_diagram_ready(
    session: AssessmentSession,
    *,
    total_questions: int,
    for_index: int,
    question: dict[str, Any],
) -> None:
    _write_cache(
        session,
        {
            "status": "ready",
            "total_questions": total_questions,
            "for_index": for_index,
            "question": question,
            "error": None,
            "started_at": None,
        },
    )


def set_diagram_failed(
    session: AssessmentSession,
    *,
    total_questions: int,
    for_index: int,
    error: str,
) -> None:
    _write_cache(
        session,
        {
            "status": "failed",
            "total_questions": total_questions,
            "for_index": for_index,
            "question": None,
            "error": error,
            "started_at": None,
        },
    )


def consume_diagram_ready(session: AssessmentSession) -> dict[str, Any] | None:
    cache = get_diagram_cache(session)
    if cache.get("status") != "ready" or not cache.get("question"):
        return None
    payload = dict(cache)
    _write_cache(
        session,
        {
            "status": "idle",
            "total_questions": cache.get("total_questions"),
            "for_index": None,
            "question": None,
            "error": None,
            "started_at": None,
        },
    )
    return payload


__all__ = [
    "consume_diagram_ready",
    "get_diagram_cache",
    "set_diagram_failed",
    "set_diagram_generating",
    "set_diagram_ready",
]
