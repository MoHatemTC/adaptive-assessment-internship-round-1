"""Celery tasks: build radar report after session completion."""

from __future__ import annotations

import asyncio

from app.core.database import async_session
from app.core.logging import get_logger
from app.workers.celery_app import celery_app

_logger = get_logger(__name__)


def _run_async(coro):
    return asyncio.run(coro)


@celery_app.task(name="reports.build_session_radar")
def build_session_radar_report(session_id: str) -> dict[str, str]:
    """Build radar report for a completed session (Abutaleb triggers via complete)."""
    from app.agent.nodes.judge import persist_session_judge_result, run_session_judge
    from app.reports.service import build_session_radar_report as _build

    async def _inner() -> dict[str, str]:
        async with async_session() as db:
            judge = await run_session_judge(db, session_id)
            await persist_session_judge_result(db, judge)
            report = await _build(db, session_id)
            await db.commit()
            payload = report.model_dump(mode="json")
            payload["status"] = "built"
            return payload

    try:
        payload = _run_async(_inner())
        _logger.info("report_task_complete", **payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        _logger.exception("report_task_failed", session_id=session_id, error=str(exc))
        raise


__all__ = ["build_session_radar_report"]
