"""Prometheus hooks for timed code assessment sessions."""

from __future__ import annotations

from app.core.metrics import active_sessions
from app.features.code.models import CodeAssessmentSession, SessionStatus


def on_session_started() -> None:
    active_sessions.inc()


def transition_session_status(
    assessment: CodeAssessmentSession,
    new_status: SessionStatus,
) -> None:
    """Update session status and adjust active session gauge when leaving ACTIVE."""
    if assessment.status == SessionStatus.ACTIVE and new_status != SessionStatus.ACTIVE:
        active_sessions.dec()
    assessment.status = new_status
