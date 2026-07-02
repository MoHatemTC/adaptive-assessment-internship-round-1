"""Celery tasks: session judge and radar report build (split chain)."""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.database import async_session
from app.core.logging import get_logger
from app.workers.celery_app import celery_app

_logger = get_logger(__name__)
_REPORT_TASK_OPTS: dict[str, object] = {
    "autoretry_for": (Exception,),
    "retry_backoff": True,
    "retry_backoff_max": 60,
    "retry_jitter": True,
    "max_retries": 3,
    "time_limit": 300,
    "soft_time_limit": 270,
}


def _run_async(coro):
    return asyncio.run(coro)


def _session_id_from_pipeline_state(pipeline_state: dict[str, Any] | str) -> str:
    if isinstance(pipeline_state, str):
        return pipeline_state
    session_id = pipeline_state.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("pipeline state missing session_id")
    return session_id


@celery_app.task(name="reports.run_session_judge", **_REPORT_TASK_OPTS)
def run_session_judge_task(session_id: str) -> dict[str, str]:
    """Run the LLM judge for a completed session (isolated from report build)."""
    from app.agent.nodes.judge import (
        persist_session_judge_result,
        run_session_judge,
        store_pending_judge_review,
    )
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
            await db.commit()
            return {"session_id": session_id, "status": "confirmed"}

    try:
        payload = _run_async(_inner())
        _logger.info("judge_task_complete", **payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        _logger.exception("judge_task_failed", session_id=session_id, error=str(exc))
        raise


@celery_app.task(name="reports.build_session_radar", **_REPORT_TASK_OPTS)
def build_session_radar_report(pipeline_state: dict[str, str] | str) -> dict[str, str]:
    """Build radar report after judge confirmation (or pass-through on HITL hold)."""
    from app.reports.service import build_session_radar_report as _build

    session_id = _session_id_from_pipeline_state(pipeline_state)
    if isinstance(pipeline_state, dict) and pipeline_state.get("status") == (
        "pending_admin_review"
    ):
        return pipeline_state

    async def _inner() -> dict[str, str]:
        async with async_session() as db:
            report = await _build(db, session_id)
            await db.commit()
            payload = report.model_dump(mode="json")
            payload["status"] = "built"
            return payload

    try:
        payload = _run_async(_inner())
        _logger.info("report_task_complete", session_id=session_id, status=payload.get("status"))
        return payload
    except Exception as exc:  # noqa: BLE001
        _logger.exception("report_task_failed", session_id=session_id, error=str(exc))
        raise


@celery_app.task(name="reports.finalize_approved_session", **_REPORT_TASK_OPTS)
def finalize_approved_session_report(session_id: str) -> dict[str, str]:
    """Build radar report after admin approves a held judge review."""
    return build_session_radar_report(session_id)


__all__ = [
    "build_session_radar_report",
    "finalize_approved_session_report",
    "run_session_judge_task",
]
