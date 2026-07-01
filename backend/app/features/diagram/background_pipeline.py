"""Deferred diagram grading, memory extraction, and next-question generation."""

from __future__ import annotations

import asyncio

from app.config import get_settings
from app.core.database import async_session
from app.core.logging import get_logger
from app.features.diagram.evaluation import evaluate_diagram_answer
from app.features.diagram.llm_generation import generate_and_store_next_diagram
from app.features.diagram.service import grade_answer, submit_response_record
from app.features.diagram.session_blueprint import diagram_blueprint_context
from app.features.diagram.session_cache import (
    set_diagram_failed,
    set_diagram_generating,
    set_diagram_ready,
)
from app.sessions.models import AssessmentSession

from app.features.diagram.models import DiagramQuestion, DiagramResponse

_logger = get_logger(__name__)


def async_pipeline_enabled() -> bool:
    return get_settings().DIAGRAM_ASYNC_PIPELINE


def _generation_timeout_seconds() -> float:
    return max(30.0, float(get_settings().DIAGRAM_GENERATION_TIMEOUT_SECONDS))


async def _mark_diagram_failed(
    session_id: str,
    *,
    for_index: int,
    total_questions: int,
    error: str,
) -> None:
    async with async_session() as db:
        session = await db.get(AssessmentSession, session_id)
        if session is None:
            return
        set_diagram_failed(
            session,
            total_questions=total_questions,
            for_index=for_index,
            error=error,
        )
        await db.commit()


async def _run_post_answer_pipeline(
    *,
    session_id: str,
    question_index: int,
    diagram_response_id: int,
    question_id: int,
    answer_text: str,
) -> None:
    next_index = question_index + 1
    budget = 1
    async with async_session() as db:
        session = await db.get(AssessmentSession, session_id)
        if session is None:
            return
        try:
            _session, blueprint, budget, profile = await diagram_blueprint_context(
                db, session_id
            )
            question = await db.get(DiagramQuestion, question_id)
            response = await db.get(DiagramResponse, diagram_response_id)
            if question is None or response is None:
                return

            grading = await grade_answer(
                correct_label=question.correct_label,
                rubric=question.rubric,
                answer_text=answer_text,
            )
            response.score = grading["score"]
            response.grading_feedback = grading["feedback"]
            await db.flush()

            await evaluate_diagram_answer(
                session_id=session_id,
                question_index=question_index,
                diagram_response_id=diagram_response_id,
                db=db,
            )

            next_index = question_index + 1
            if next_index >= budget:
                await db.commit()
                return

            session = await db.get(AssessmentSession, session_id)
            if session is None:
                return
            set_diagram_generating(
                session,
                total_questions=budget,
                for_index=next_index,
            )
            await db.commit()

            generated = await asyncio.wait_for(
                generate_and_store_next_diagram(
                    db=db,
                    next_plan={
                        "next_question_index": next_index,
                        "memory_summary": "",
                    },
                    learner_profile=profile,
                    admin_config=blueprint,
                ),
                timeout=_generation_timeout_seconds(),
            )
            session = await db.get(AssessmentSession, session_id)
            if session is None:
                return
            set_diagram_ready(
                session,
                total_questions=budget,
                for_index=next_index,
                question=generated,
            )
            await db.commit()
            _logger.info(
                "diagram_next_question_ready",
                session_id=session_id,
                question_index=next_index,
            )
        except asyncio.TimeoutError:
            await db.rollback()
            _logger.error(
                "diagram_post_answer_pipeline_timeout",
                session_id=session_id,
                question_index=question_index,
            )
            await _mark_diagram_failed(
                session_id,
                for_index=next_index,
                total_questions=budget,
                error="Question generation timed out",
            )
        except Exception:
            await db.rollback()
            _logger.exception(
                "diagram_post_answer_pipeline_failed",
                session_id=session_id,
                question_index=question_index,
            )
            await _mark_diagram_failed(
                session_id,
                for_index=next_index,
                total_questions=budget,
                error="Question generation failed",
            )


async def _run_start_pipeline(*, session_id: str) -> None:
    budget = 1
    async with async_session() as db:
        session = await db.get(AssessmentSession, session_id)
        if session is None:
            return
        try:
            _session, blueprint, budget, profile = await diagram_blueprint_context(
                db, session_id
            )
            generated = await asyncio.wait_for(
                generate_and_store_next_diagram(
                    db=db,
                    next_plan={"next_question_index": 0, "memory_summary": ""},
                    learner_profile=profile,
                    admin_config=blueprint,
                ),
                timeout=_generation_timeout_seconds(),
            )
            session = await db.get(AssessmentSession, session_id)
            if session is None:
                return
            set_diagram_ready(
                session,
                total_questions=budget,
                for_index=0,
                question=generated,
            )
            await db.commit()
            _logger.info("diagram_first_question_ready", session_id=session_id)
        except asyncio.TimeoutError:
            await db.rollback()
            _logger.error("diagram_start_pipeline_timeout", session_id=session_id)
            await _mark_diagram_failed(
                session_id,
                for_index=0,
                total_questions=budget,
                error="Question generation timed out",
            )
        except Exception:
            await db.rollback()
            _logger.exception("diagram_start_pipeline_failed", session_id=session_id)
            await _mark_diagram_failed(
                session_id,
                for_index=0,
                total_questions=budget,
                error="Question generation failed",
            )


def schedule_diagram_post_answer(
    *,
    session_id: str,
    question_index: int,
    diagram_response_id: int,
    question_id: int,
    answer_text: str,
    force: bool = False,
) -> None:
    from app.workers.pipeline_dispatch import dispatch_pipeline_task

    dispatch_pipeline_task(
        "pipelines.diagram.post_answer",
        kwargs={
            "session_id": session_id,
            "question_index": question_index,
            "diagram_response_id": diagram_response_id,
            "question_id": question_id,
            "answer_text": answer_text,
        },
        background_coro=_run_post_answer_pipeline(
            session_id=session_id,
            question_index=question_index,
            diagram_response_id=diagram_response_id,
            question_id=question_id,
            answer_text=answer_text,
        ),
        background_key=f"diagram:post:{session_id}",
        force=force,
    )


def schedule_diagram_start(*, session_id: str, force: bool = False) -> None:
    from app.workers.pipeline_dispatch import dispatch_pipeline_task

    dispatch_pipeline_task(
        "pipelines.diagram.start",
        kwargs={"session_id": session_id},
        background_coro=_run_start_pipeline(session_id=session_id),
        background_key=f"diagram:start:{session_id}",
        force=force,
    )


__all__ = [
    "async_pipeline_enabled",
    "schedule_diagram_post_answer",
    "schedule_diagram_start",
]
