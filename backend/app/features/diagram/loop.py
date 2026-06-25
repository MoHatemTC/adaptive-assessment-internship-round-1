"""Diagram adaptive loop — thin orchestrator."""
from __future__ import annotations

from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logging import get_logger
from app.features.diagram.evaluation import evaluate_diagram_answer

logger = get_logger(__name__)


async def run_diagram_loop(
    session_id: str,
    question_index: int,
    diagram_response_id: int,
    total_questions: int,
    db: AsyncSession,
) -> dict[str, Any]:
    eval_result = await evaluate_diagram_answer(
        session_id=session_id,
        question_index=question_index,
        diagram_response_id=diagram_response_id,
        db=db,
    )
    is_complete = (question_index + 1) >= total_questions

    logger.info(
        "diagram_loop_completed",
        session_id=session_id,
        question_index=question_index,
        is_complete=is_complete,
    )

    return {
        "is_complete": is_complete,
        "memory_card": eval_result.get("memory_card"),
        "memory_summary": eval_result.get("memory_summary"),
    }
