"""Deferred MCQ memory extraction and next-question generation."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from app.core.database import async_session
from app.core.logging import get_logger
from app.features.mcq.analysis import analyze_mcq_session
from app.features.mcq.evaluation import extract_mcq_memory_for_response
from app.features.mcq.llm_generation import generate_and_store_next_mcq
from app.features.mcq.session_blueprint import mcq_blueprint_context
from app.features.mcq.session_cache import (
    set_mcq_failed,
    set_mcq_generating,
    set_mcq_ready,
)
from app.sessions.models import AssessmentSession

_logger = get_logger(__name__)

_DEFAULT_GENERATION_TIMEOUT_SECONDS = 120


def async_pipeline_enabled() -> bool:
    return os.environ.get("MCQ_ASYNC_PIPELINE", "true").lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _generation_timeout_seconds() -> float:
    raw = os.environ.get(
        "MCQ_GENERATION_TIMEOUT_SECONDS",
        str(_DEFAULT_GENERATION_TIMEOUT_SECONDS),
    )
    try:
        return max(30.0, float(raw))
    except ValueError:
        return float(_DEFAULT_GENERATION_TIMEOUT_SECONDS)


async def _mark_mcq_failed(
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
        set_mcq_failed(
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
    mcq_response_id: int,
    total_questions: int,
) -> None:
    next_index = question_index + 1
    budget = total_questions
    async with async_session() as db:
        session = await db.get(AssessmentSession, session_id)
        if session is None:
            return
        try:
            _session, blueprint, budget, profile = await mcq_blueprint_context(
                db, session_id
            )
            await extract_mcq_memory_for_response(
                session_id=session_id,
                question_index=question_index,
                mcq_response_id=mcq_response_id,
                db=db,
            )
            await analyze_mcq_session(session_id, question_index)

            next_index = question_index + 1
            if next_index >= budget:
                await db.commit()
                return

            set_mcq_generating(
                session,
                total_questions=budget,
                for_index=next_index,
            )
            await db.commit()

            generated = await asyncio.wait_for(
                generate_and_store_next_mcq(
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
            set_mcq_ready(
                session,
                total_questions=budget,
                for_index=next_index,
                question=generated,
            )
            await db.commit()
            _logger.info(
                "mcq_next_question_ready",
                session_id=session_id,
                question_index=next_index,
            )
        except asyncio.TimeoutError:
            await db.rollback()
            _logger.error(
                "mcq_post_answer_pipeline_timeout",
                session_id=session_id,
                question_index=question_index,
            )
            await _mark_mcq_failed(
                session_id,
                for_index=next_index,
                total_questions=budget,
                error="Question generation timed out",
            )
        except Exception:
            await db.rollback()
            _logger.exception(
                "mcq_post_answer_pipeline_failed",
                session_id=session_id,
                question_index=question_index,
            )
            await _mark_mcq_failed(
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
            _session, blueprint, budget, profile = await mcq_blueprint_context(
                db, session_id
            )
            generated = await asyncio.wait_for(
                generate_and_store_next_mcq(
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
            set_mcq_ready(
                session,
                total_questions=budget,
                for_index=0,
                question=generated,
            )
            await db.commit()
            _logger.info("mcq_first_question_ready", session_id=session_id)
        except asyncio.TimeoutError:
            await db.rollback()
            _logger.error("mcq_start_pipeline_timeout", session_id=session_id)
            await _mark_mcq_failed(
                session_id,
                for_index=0,
                total_questions=budget,
                error="Question generation timed out",
            )
        except Exception:
            await db.rollback()
            _logger.exception("mcq_start_pipeline_failed", session_id=session_id)
            await _mark_mcq_failed(
                session_id,
                for_index=0,
                total_questions=budget,
                error="Question generation failed",
            )


def schedule_mcq_post_answer(
    *,
    session_id: str,
    question_index: int,
    mcq_response_id: int,
    total_questions: int,
    force: bool = False,
) -> None:
    from app.workers.pipeline_dispatch import dispatch_pipeline_task

    dispatch_pipeline_task(
        "pipelines.mcq.post_answer",
        kwargs={
            "session_id": session_id,
            "question_index": question_index,
            "mcq_response_id": mcq_response_id,
            "total_questions": total_questions,
        },
        background_coro=_run_post_answer_pipeline(
            session_id=session_id,
            question_index=question_index,
            mcq_response_id=mcq_response_id,
            total_questions=total_questions,
        ),
        background_key=f"mcq:post:{session_id}",
        force=force,
    )


def schedule_mcq_start(*, session_id: str, force: bool = False) -> None:
    from app.workers.pipeline_dispatch import dispatch_pipeline_task

    dispatch_pipeline_task(
        "pipelines.mcq.start",
        kwargs={"session_id": session_id},
        background_coro=_run_start_pipeline(session_id=session_id),
        background_key=f"mcq:start:{session_id}",
        force=force,
    )


__all__ = [
    "async_pipeline_enabled",
    "schedule_mcq_post_answer",
    "schedule_mcq_start",
]
