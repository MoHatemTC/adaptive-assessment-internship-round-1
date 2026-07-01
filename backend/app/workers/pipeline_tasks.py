"""Celery tasks for MCQ/diagram pipelines and code sandbox grading."""

from __future__ import annotations

from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.core.database import async_session
from app.core.logging import get_logger
from app.core.metrics import celery_tasks_total
from app.features.code.background_grading import run_llm_grade_upgrade
from app.features.code.models import CodeChallenge, CodeSubmission
from app.features.code.sandbox_execution import (
    mark_submission_failed,
    run_sandbox_for_submission,
)
from app.features.diagram.background_pipeline import (
    _run_post_answer_pipeline as diagram_post_answer,
    _run_start_pipeline as diagram_start,
)
from app.features.mcq.background_pipeline import (
    _run_post_answer_pipeline as mcq_post_answer,
    _run_start_pipeline as mcq_start,
)
from app.workers.async_runner import run_async
from app.workers.celery_app import celery_app

_logger = get_logger(__name__)

_PIPELINE_TASK_OPTS: dict[str, object] = {
    "bind": True,
    "autoretry_for": (Exception,),
    "retry_backoff": True,
    "retry_backoff_max": 60,
    "retry_jitter": True,
    "max_retries": 3,
    "time_limit": 300,
    "soft_time_limit": 270,
}


def _record_task(task_name: str, status: str) -> None:
    celery_tasks_total.labels(task_name=task_name, status=status).inc()


@celery_app.task(name="pipelines.mcq.post_answer", **_PIPELINE_TASK_OPTS)
def mcq_post_answer_task(
    *,
    session_id: str,
    question_index: int,
    mcq_response_id: int,
    total_questions: int,
) -> dict[str, str]:
    """Run MCQ memory extraction and next-question generation on a worker."""
    task_name = "pipelines.mcq.post_answer"
    try:
        run_async(
            mcq_post_answer(
                session_id=session_id,
                question_index=question_index,
                mcq_response_id=mcq_response_id,
                total_questions=total_questions,
            )
        )
        _record_task(task_name, "success")
        return {"session_id": session_id, "status": "completed"}
    except Exception:  # noqa: BLE001
        _record_task(task_name, "error")
        _logger.exception("mcq_post_answer_task_failed", session_id=session_id)
        raise


@celery_app.task(name="pipelines.mcq.start", **_PIPELINE_TASK_OPTS)
def mcq_start_task(*, session_id: str) -> dict[str, str]:
    """Generate the first MCQ for a session on a worker."""
    task_name = "pipelines.mcq.start"
    try:
        run_async(mcq_start(session_id=session_id))
        _record_task(task_name, "success")
        return {"session_id": session_id, "status": "completed"}
    except Exception:  # noqa: BLE001
        _record_task(task_name, "error")
        _logger.exception("mcq_start_task_failed", session_id=session_id)
        raise


@celery_app.task(name="pipelines.diagram.post_answer", **_PIPELINE_TASK_OPTS)
def diagram_post_answer_task(
    *,
    session_id: str,
    question_index: int,
    diagram_response_id: int,
    question_id: int,
    answer_text: str,
) -> dict[str, str]:
    """Run diagram memory extraction and next-question generation on a worker."""
    task_name = "pipelines.diagram.post_answer"
    try:
        run_async(
            diagram_post_answer(
                session_id=session_id,
                question_index=question_index,
                diagram_response_id=diagram_response_id,
                question_id=question_id,
                answer_text=answer_text,
            )
        )
        _record_task(task_name, "success")
        return {"session_id": session_id, "status": "completed"}
    except Exception:  # noqa: BLE001
        _record_task(task_name, "error")
        _logger.exception("diagram_post_answer_task_failed", session_id=session_id)
        raise


@celery_app.task(name="pipelines.diagram.start", **_PIPELINE_TASK_OPTS)
def diagram_start_task(*, session_id: str) -> dict[str, str]:
    """Generate the first diagram question for a session on a worker."""
    task_name = "pipelines.diagram.start"
    try:
        run_async(diagram_start(session_id=session_id))
        _record_task(task_name, "success")
        return {"session_id": session_id, "status": "completed"}
    except Exception:  # noqa: BLE001
        _record_task(task_name, "error")
        _logger.exception("diagram_start_task_failed", session_id=session_id)
        raise


@celery_app.task(name="pipelines.code.llm_grade_upgrade", **_PIPELINE_TASK_OPTS)
def code_llm_grade_upgrade_task(
    *,
    grade_id: int,
    session_id: str,
    question_index: int,
    difficulty: str,
) -> dict[str, str]:
    """Upgrade a code grade rubric with full LLM feedback on a worker."""
    task_name = "pipelines.code.llm_grade_upgrade"
    try:
        run_async(
            run_llm_grade_upgrade(
                grade_id=grade_id,
                session_id=session_id,
                question_index=question_index,
                difficulty=difficulty,
            )
        )
        _record_task(task_name, "success")
        return {"grade_id": str(grade_id), "status": "completed"}
    except Exception:  # noqa: BLE001
        _record_task(task_name, "error")
        _logger.exception(
            "code_llm_grade_upgrade_task_failed",
            grade_id=grade_id,
            session_id=session_id,
        )
        raise


@celery_app.task(name="pipelines.code.execute_submission", **_PIPELINE_TASK_OPTS)
def code_execute_submission_task(*, submission_id: int) -> dict[str, str]:
    """Run E2B sandbox execution for a persisted submission on a worker."""

    async def _inner() -> dict[str, str]:
        async with async_session() as db:
            submission_result = await db.exec(
                select(CodeSubmission).where(CodeSubmission.id == submission_id)
            )
            submission = submission_result.first()
            if submission is None:
                raise ValueError(f"submission not found: {submission_id}")

            challenge_result = await db.exec(
                select(CodeChallenge)
                .where(CodeChallenge.id == submission.challenge_id)
                .options(selectinload(CodeChallenge.test_cases))
            )
            challenge = challenge_result.first()
            if challenge is None:
                raise ValueError(f"challenge not found for submission {submission_id}")
            if not challenge.test_cases:
                raise ValueError(
                    f"challenge {challenge.id} has no test cases for submission {submission_id}"
                )

            try:
                await run_sandbox_for_submission(
                    db,
                    submission=submission,
                    challenge=challenge,
                    submitted_code=submission.submitted_code,
                )
            except Exception as exc:
                await mark_submission_failed(
                    db,
                    submission=submission,
                    error=str(exc),
                )
                raise
            return {"submission_id": str(submission_id), "status": "completed"}

    task_name = "pipelines.code.execute_submission"
    try:
        payload = run_async(_inner())
        _record_task(task_name, "success")
        return payload
    except Exception:  # noqa: BLE001
        _record_task(task_name, "error")
        _logger.exception(
            "code_execute_submission_task_failed",
            submission_id=submission_id,
        )
        raise


__all__ = [
    "code_execute_submission_task",
    "code_llm_grade_upgrade_task",
    "diagram_post_answer_task",
    "diagram_start_task",
    "mcq_post_answer_task",
    "mcq_start_task",
]
