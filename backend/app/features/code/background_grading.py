"""Background LLM grading for fast adaptive-submit responses."""

from __future__ import annotations

import os

from app.core.database import async_session
from app.core.logging import get_logger
from app.features.code import evaluation, grading

_logger = get_logger(__name__)


def async_grading_enabled() -> bool:
    """Return True when sandbox-first submit with deferred LLM grading is enabled."""
    return os.environ.get("CODE_ASYNC_GRADING", "true").lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


async def run_llm_grade_upgrade(
    *,
    grade_id: int,
    session_id: str,
    question_index: int,
    difficulty: str,
) -> None:
    """Replace sandbox-heuristic rubric feedback with a full LLM rubric."""
    async with async_session() as db:
        try:
            grade = await grading.upgrade_grade_with_llm(db, grade_id)
            await evaluation.refresh_memory_card_for_grade(
                db,
                grade.id,
                difficulty,
            )
            await db.commit()
            _logger.info(
                "code_llm_grade_upgrade_complete",
                grade_id=grade_id,
                session_id=session_id,
                question_index=question_index,
            )
        except Exception:
            await db.rollback()
            _logger.exception(
                "code_llm_grade_upgrade_failed",
                grade_id=grade_id,
                session_id=session_id,
                question_index=question_index,
            )


def schedule_llm_grade_upgrade(
    *,
    grade_id: int,
    session_id: str,
    question_index: int,
    difficulty: str,
) -> None:
    """Fire-and-forget LLM rubric upgrade on a worker or the running event loop."""
    from app.workers.pipeline_dispatch import dispatch_pipeline_task

    dispatch_pipeline_task(
        "pipelines.code.llm_grade_upgrade",
        kwargs={
            "grade_id": grade_id,
            "session_id": session_id,
            "question_index": question_index,
            "difficulty": difficulty,
        },
        background_coro=run_llm_grade_upgrade(
            grade_id=grade_id,
            session_id=session_id,
            question_index=question_index,
            difficulty=difficulty,
        ),
        background_key=f"code:grade:{grade_id}",
    )


__all__ = [
    "async_grading_enabled",
    "run_llm_grade_upgrade",
    "schedule_llm_grade_upgrade",
]
