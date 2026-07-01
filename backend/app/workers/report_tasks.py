"""Celery tasks: build radar report after session completion."""

from __future__ import annotations

import asyncio
import json

from app.core.database import async_session
from app.core.logging import get_logger
from app.workers.celery_app import celery_app

_logger = get_logger(__name__)


def _run_async(coro):
    return asyncio.run(coro)


def _learner_email_from_profile(raw: str) -> str | None:
    try:
        profile = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(profile, dict):
        return None
    email = profile.get("email")
    return email if isinstance(email, str) and email.strip() else None


@celery_app.task(name="reports.build_session_radar")
def build_session_radar_report(session_id: str) -> dict[str, str]:
    """Build radar report for a completed session after judge validation."""
    from app.agent.nodes.judge import (
        persist_session_judge_result,
        run_session_judge,
        store_pending_judge_review,
    )
    from app.reports.service import build_session_radar_report as _build
    from app.sessions.models import AssessmentSession

    async def _inner() -> dict[str, str]:
        async with async_session() as db:
            session = await db.get(AssessmentSession, session_id)
            if session is None:
                raise ValueError(f"session not found: {session_id}")

            judge = await run_session_judge(db, session_id)
            if judge.review_status == "pending_admin_review":
                await store_pending_judge_review(db, session, judge)
                await db.commit()
                return {
                    "session_id": session_id,
                    "status": "pending_admin_review",
                    "review_reason": judge.review_reason or "",
                }

            await persist_session_judge_result(db, judge)
            report = await _build(db, session_id)
            await db.commit()
            return {
                "session_id": session_id,
                "status": "built",
                "overall_score": str(report.overall_score),
            }

    try:
        payload = _run_async(_inner())
        _logger.info("report_task_complete", **payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        _logger.exception("report_task_failed", session_id=session_id, error=str(exc))
        raise


@celery_app.task(name="reports.finalize_approved_session")
def finalize_approved_session_report(session_id: str) -> dict[str, str]:
    """Build radar report after admin approves a held judge review."""
    from app.reports.service import build_session_radar_report as _build

    async def _inner() -> dict[str, str]:
        async with async_session() as db:
            report = await _build(db, session_id)
            await db.commit()
            return {
                "session_id": session_id,
                "status": "built",
                "overall_score": str(report.overall_score),
            }

    try:
        payload = _run_async(_inner())
        _logger.info("approved_report_task_complete", **payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        _logger.exception(
            "approved_report_task_failed", session_id=session_id, error=str(exc)
        )
        raise


__all__ = ["build_session_radar_report", "finalize_approved_session_report"]
