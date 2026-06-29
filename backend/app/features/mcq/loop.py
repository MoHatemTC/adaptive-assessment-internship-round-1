"""MCQ adaptive loop — orchestrates evaluation, analysis, then the shared
adaptation agent.

This is a thin orchestrator. It runs the silent evaluation layer
(:func:`app.features.mcq.evaluation.evaluate_mcq_answer`), which grades the
answer, persists ``score``/``grading_feedback`` and extracts a memory card,
then the skill taxonomy analysis layer
(:func:`app.features.mcq.analysis.analyze_mcq_session`), which aggregates this
session's MCQ memory cards into a ``SkillDimensionScore`` row — mirroring
voice's ``analyze_voice_session`` so the admin radar report has MCQ data to
display. Per platform design (Law 19) the MCQ tool still does NOT implement
its own next-question adaptation layer: the shared agent
(:mod:`app.features.adaptation`) reads ``MCQResponse.score`` via
``_fetch_mcq_answers`` to drive next-question selection.

Nothing returned here is for the learner — grading detail stays server-side.
"""

from __future__ import annotations

from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logging import get_logger
from app.features.mcq.analysis import analyze_mcq_session
from app.features.mcq.evaluation import evaluate_mcq_answer

logger = get_logger(__name__)


async def run_mcq_loop(
    session_id: str,
    question_index: int,
    mcq_response_id: int,
    total_questions: int,
    db: AsyncSession,
) -> dict[str, Any]:
    """Run one complete MCQ adaptive turn.

    Calls the evaluation layer (which grades, persists ``score``/dimension, and
    runs the memory agent), then the analysis layer (which aggregates this
    session's MCQ memory cards into a ``SkillDimensionScore`` row), then reports
    whether the assessment is complete. The shared adaptation agent separately
    reads ``MCQResponse.score`` via ``_fetch_mcq_answers`` to choose the next
    question's difficulty and dimension.

    Args:
        session_id: Platform assessment session UUID.
        question_index: Zero-based index of the question just answered.
        mcq_response_id: Primary key of the just-submitted :class:`MCQResponse`.
        total_questions: Total questions in this assessment (from the blueprint).
        db: Active async database session.

    Returns:
        A dict with keys ``is_complete`` (bool), ``memory_card`` (internal only),
        and ``memory_summary`` (internal only). It deliberately omits ``score``,
        ``passed``, and every other grading detail.
    """
    # Layer 1 — grade silently and extract a memory card.
    eval_result = await evaluate_mcq_answer(
        session_id=session_id,
        question_index=question_index,
        mcq_response_id=mcq_response_id,
        db=db,
    )

    # Layer 7 — aggregate this session's MCQ memory cards into a
    # SkillDimensionScore row, feeding the admin radar report.
    await analyze_mcq_session(session_id, question_index)

    is_complete = (question_index + 1) >= total_questions

    logger.info(
        "mcq_loop_completed",
        session_id=session_id,
        question_index=question_index,
        is_complete=is_complete,
    )

    return {
        "is_complete": is_complete,
        "memory_card": eval_result.get("memory_card"),
        "memory_summary": eval_result.get("memory_summary"),
    }


async def run_mcq_loop_fast(
    session_id: str,
    question_index: int,
    mcq_response_id: int,
    total_questions: int,
    db: AsyncSession,
) -> dict[str, Any]:
    """Fast path: objective grade only; memory/analysis run in background."""
    await evaluate_mcq_answer(
        session_id=session_id,
        question_index=question_index,
        mcq_response_id=mcq_response_id,
        db=db,
        skip_memory=True,
    )
    is_complete = (question_index + 1) >= total_questions
    logger.info(
        "mcq_loop_fast_completed",
        session_id=session_id,
        question_index=question_index,
        is_complete=is_complete,
    )
    return {"is_complete": is_complete, "memory_card": None, "memory_summary": ""}
