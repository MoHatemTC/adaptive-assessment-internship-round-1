"""FastAPI routes for the MCQ feature."""

from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.deps import get_db
from app.core.logging import get_logger
from app.features.mcq.background_pipeline import (
    async_pipeline_enabled,
    schedule_mcq_post_answer,
    schedule_mcq_start,
)
from app.features.mcq.llm_generation import generate_and_store_next_mcq
from app.features.mcq.loop import run_mcq_loop, run_mcq_loop_fast
from app.features.mcq.models import MCQResponse
from app.features.mcq.schemas import (
    MCQAnswerRequest,
    MCQAnswerResponse,
    MCQCreateRequest,
    MCQNextOption,
    MCQNextQuestion,
    MCQPendingQuestionResponse,
    MCQQuestionResponse,
    MCQStartResponse,
    MCQSubmitRequest,
    MCQSubmitResponse,
)
from app.features.mcq.session_blueprint import mcq_blueprint_context
from app.features.mcq.session_cache import (
    consume_mcq_ready,
    get_mcq_cache,
    set_mcq_generating,
)
from app.shared.async_question_cache import generation_is_stale, generation_should_schedule
from app.features.mcq.service import (
    build_submit_response,
    create_question,
    get_correct_option,
    get_question,
    grade_answer,
    normalize_option_id,
)
from app.sessions.models import AssessmentSession

_logger = get_logger(__name__)

router = APIRouter(prefix="/mcq", tags=["mcq"])


def _serialize_generated(generated: dict) -> MCQNextQuestion:
    return MCQNextQuestion(
        id=generated["id"],
        question_text=generated["question_text"],
        difficulty=generated["difficulty"],
        dimension=generated.get("dimension"),
        options=[
            MCQNextOption(label=o["label"], text=o["text"])
            for o in generated["options"]
        ],
    )


def _pending_from_cache(
  cache: dict,
) -> MCQPendingQuestionResponse:
    question = cache.get("question")
    error = cache.get("error")
    return MCQPendingQuestionResponse(
        status=str(cache.get("status", "idle")),
        total_questions=int(cache.get("total_questions") or 1),
        question=_serialize_generated(question) if isinstance(question, dict) else None,
        error=str(error) if isinstance(error, str) and error else None,
    )


@router.get("/health")
def mcq_health_check() -> Dict[str, str]:
    return {"status": "ready", "feature": "mcq"}


@router.post("/questions", response_model=MCQQuestionResponse)
async def create_mcq_question(
    payload: MCQCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, object]:
    return await create_question(
        db=db,
        question_text=payload.question_text,
        correct_option=payload.correct_option,
        options=[{"label": o.label, "text": o.text} for o in payload.options],
        difficulty=payload.difficulty,
    )


@router.get("/questions/{question_id}", response_model=MCQQuestionResponse)
async def get_mcq_question(
    question_id: int,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, object]:
    return await get_question(db=db, question_id=question_id)


@router.post("/submit", response_model=MCQSubmitResponse)
async def submit_mcq_answer(
    payload: MCQSubmitRequest,
    db: AsyncSession = Depends(get_db),
) -> MCQSubmitResponse:
    await build_submit_response(
        db=db,
        question_id=payload.question_id,
        selected_option=payload.selected_option,
        session_id=payload.session_id,
        learner_id=payload.learner_id,
    )
    return MCQSubmitResponse(received=True, question_id=payload.question_id)


@router.get(
    "/sessions/{session_id}/pending-question",
    response_model=MCQPendingQuestionResponse,
)
async def get_pending_mcq_question(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> MCQPendingQuestionResponse:
    """Poll for the next learner-safe MCQ after async generation."""
    from app.proctoring.enforcement import ensure_tool_session_allowed

    await ensure_tool_session_allowed(db, session_id)
    session = await db.get(AssessmentSession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")

    cache = get_mcq_cache(session)
    if cache.get("status") == "ready" and cache.get("question"):
        consumed = consume_mcq_ready(session)
        await db.commit()
        if consumed and consumed.get("question"):
            return MCQPendingQuestionResponse(
                status="ready",
                total_questions=int(consumed.get("total_questions") or 1),
                question=_serialize_generated(consumed["question"]),
            )
    return _pending_from_cache(cache)


@router.post(
    "/sessions/{session_id}/start",
    response_model=MCQStartResponse,
)
async def start_adaptive_mcq_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> MCQStartResponse:
    """Kick off first-question generation; poll pending-question until ready."""
    from app.proctoring.enforcement import ensure_tool_session_allowed

    await ensure_tool_session_allowed(db, session_id)
    try:
        session, blueprint, total_questions, profile = await mcq_blueprint_context(
            db, session_id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    cache = get_mcq_cache(session)
    if cache.get("status") == "ready" and cache.get("question"):
        consumed = consume_mcq_ready(session)
        await db.commit()
        if consumed and consumed.get("question"):
            return MCQStartResponse(
                status="ready",
                total_questions=int(consumed.get("total_questions") or total_questions),
                question=_serialize_generated(consumed["question"]),
            )

    if not async_pipeline_enabled():
        generated = await generate_and_store_next_mcq(
            db=db,
            next_plan={"next_question_index": 0, "memory_summary": ""},
            learner_profile=profile,
            admin_config=blueprint,
        )
        await db.commit()
        return MCQStartResponse(
            status="ready",
            total_questions=total_questions,
            question=_serialize_generated(generated),
        )

    if generation_should_schedule(cache):
        set_mcq_generating(session, total_questions=total_questions, for_index=0)
        await db.commit()
        schedule_mcq_start(
            session_id=session_id,
            force=generation_is_stale(cache),
        )

    return MCQStartResponse(
        status="generating",
        total_questions=total_questions,
        question=None,
    )


@router.post(
    "/sessions/{session_id}/answer",
    response_model=MCQAnswerResponse,
)
async def submit_adaptive_mcq_answer(
    session_id: str,
    payload: MCQAnswerRequest,
    db: AsyncSession = Depends(get_db),
) -> MCQAnswerResponse:
    from app.proctoring.enforcement import ensure_tool_session_allowed

    await ensure_tool_session_allowed(db, session_id)
    try:
        session, blueprint, total_questions, profile = await mcq_blueprint_context(
            db, session_id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    question_budget = total_questions
    correct_option = await get_correct_option(db=db, question_id=payload.question_id)
    grading = grade_answer(
        correct_option=correct_option,
        selected_option=payload.selected_option,
    )
    response = MCQResponse(
        question_id=payload.question_id,
        session_id=session_id,
        learner_id=payload.learner_id,
        selected_option=normalize_option_id(payload.selected_option),
        is_correct=grading["is_correct"],
        score=None,
    )
    db.add(response)
    await db.flush()
    mcq_response_id = response.id

    if async_pipeline_enabled():
        loop_result = await run_mcq_loop_fast(
            session_id=session_id,
            question_index=payload.question_index,
            mcq_response_id=mcq_response_id,
            total_questions=question_budget,
            db=db,
        )
        is_complete = loop_result["is_complete"]
        await db.refresh(session)
        await db.commit()

        if not is_complete:
            set_mcq_generating(
                session,
                total_questions=question_budget,
                for_index=payload.question_index + 1,
            )
            await db.commit()
            schedule_mcq_post_answer(
                session_id=session_id,
                question_index=payload.question_index,
                mcq_response_id=mcq_response_id,
                total_questions=question_budget,
            )
            return MCQAnswerResponse(
                next_question=None,
                is_complete=False,
                status="generating",
                total_questions=question_budget,
            )

        return MCQAnswerResponse(
            next_question=None,
            is_complete=True,
            status="ready",
            total_questions=question_budget,
        )

    loop_result = await run_mcq_loop(
        session_id=session_id,
        question_index=payload.question_index,
        mcq_response_id=mcq_response_id,
        total_questions=question_budget,
        db=db,
    )
    is_complete = loop_result["is_complete"]
    next_question: MCQNextQuestion | None = None
    if not is_complete:
        next_plan = {
            "next_question_index": payload.question_index + 1,
            "memory_summary": loop_result.get("memory_summary", ""),
        }
        try:
            generated = await generate_and_store_next_mcq(
                db=db,
                next_plan=next_plan,
                learner_profile=profile,
                admin_config=blueprint,
            )
            next_question = _serialize_generated(generated)
        except Exception as exc:  # noqa: BLE001
            _logger.error("mcq_next_generation_failed", error=str(exc))

    await db.commit()
    return MCQAnswerResponse(
        next_question=next_question,
        is_complete=is_complete,
        status="ready",
        total_questions=question_budget,
    )
