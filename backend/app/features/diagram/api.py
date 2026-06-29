"""FastAPI routes for the SVG diagram feature."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.deps import get_db
from app.core.logging import get_logger
from app.features.diagram.background_pipeline import (
    async_pipeline_enabled,
    schedule_diagram_post_answer,
    schedule_diagram_start,
)
from app.features.diagram.llm_generation import generate_and_store_next_diagram
from app.features.diagram.loop import run_diagram_loop
from app.features.diagram.schemas import (
    DiagramAnswerRequest,
    DiagramAnswerResponse,
    DiagramCreateRequest,
    DiagramNextQuestion,
    DiagramPendingQuestionResponse,
    DiagramQuestionResponse,
    DiagramStartResponse,
)
from app.features.diagram.service import (
    create_question,
    get_question,
    submit_response,
    submit_response_record,
)
from app.features.diagram.session_blueprint import diagram_blueprint_context
from app.features.diagram.session_cache import (
    consume_diagram_ready,
    get_diagram_cache,
    set_diagram_generating,
)
from app.shared.async_question_cache import generation_is_stale, generation_should_schedule
from app.sessions.models import AssessmentSession

_logger = get_logger(__name__)

router = APIRouter(prefix="/diagram", tags=["diagram"])


def _serialize_generated(generated: dict) -> DiagramNextQuestion:
    return DiagramNextQuestion(
        id=generated["id"],
        svg_content=generated["svg_content"],
        prompt=generated["prompt"],
        difficulty=generated["difficulty"],
        dimension=generated.get("dimension"),
    )


@router.get("/health")
def diagram_health_check() -> dict:
    return {"status": "ready", "feature": "diagram"}


@router.post("/questions", response_model=DiagramQuestionResponse)
async def create_diagram_question(
    payload: DiagramCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await create_question(
        db=db,
        svg_content=payload.svg_content,
        prompt=payload.prompt,
        correct_label=payload.correct_label,
        rubric=payload.rubric,
        difficulty=payload.difficulty,
        dimension=payload.dimension,
    )


@router.get("/questions/{question_id}", response_model=DiagramQuestionResponse)
async def get_diagram_question(
    question_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await get_question(db=db, question_id=question_id)


@router.get(
    "/sessions/{session_id}/pending-question",
    response_model=DiagramPendingQuestionResponse,
)
async def get_pending_diagram_question(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> DiagramPendingQuestionResponse:
    from app.proctoring.enforcement import ensure_tool_session_allowed

    await ensure_tool_session_allowed(db, session_id)
    session = await db.get(AssessmentSession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")

    cache = get_diagram_cache(session)
    if cache.get("status") == "ready" and cache.get("question"):
        consumed = consume_diagram_ready(session)
        await db.commit()
        if consumed and consumed.get("question"):
            return DiagramPendingQuestionResponse(
                status="ready",
                total_questions=int(consumed.get("total_questions") or 1),
                question=_serialize_generated(consumed["question"]),
            )
    return DiagramPendingQuestionResponse(
        status=str(cache.get("status", "idle")),
        total_questions=int(cache.get("total_questions") or 1),
        question=(
            _serialize_generated(cache["question"])
            if isinstance(cache.get("question"), dict)
            else None
        ),
        error=(
            str(cache["error"])
            if isinstance(cache.get("error"), str) and cache.get("error")
            else None
        ),
    )


@router.post(
    "/sessions/{session_id}/start",
    response_model=DiagramStartResponse,
)
async def start_adaptive_diagram_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> DiagramStartResponse:
    from app.proctoring.enforcement import ensure_tool_session_allowed

    await ensure_tool_session_allowed(db, session_id)
    try:
        session, blueprint, total_questions, profile = await diagram_blueprint_context(
            db, session_id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    cache = get_diagram_cache(session)
    if cache.get("status") == "ready" and cache.get("question"):
        consumed = consume_diagram_ready(session)
        await db.commit()
        if consumed and consumed.get("question"):
            return DiagramStartResponse(
                status="ready",
                total_questions=int(consumed.get("total_questions") or total_questions),
                question=_serialize_generated(consumed["question"]),
            )

    if not async_pipeline_enabled():
        generated = await generate_and_store_next_diagram(
            db=db,
            next_plan={"next_question_index": 0, "memory_summary": ""},
            learner_profile=profile,
            admin_config=blueprint,
        )
        await db.commit()
        return DiagramStartResponse(
            status="ready",
            total_questions=total_questions,
            question=_serialize_generated(generated),
        )

    if generation_should_schedule(cache):
        set_diagram_generating(session, total_questions=total_questions, for_index=0)
        await db.commit()
        schedule_diagram_start(
            session_id=session_id,
            force=generation_is_stale(cache),
        )

    return DiagramStartResponse(
        status="generating",
        total_questions=total_questions,
        question=None,
    )


@router.post(
    "/sessions/{session_id}/answer",
    response_model=DiagramAnswerResponse,
)
async def submit_adaptive_diagram_answer(
    session_id: str,
    payload: DiagramAnswerRequest,
    db: AsyncSession = Depends(get_db),
) -> DiagramAnswerResponse:
    from app.proctoring.enforcement import ensure_tool_session_allowed

    await ensure_tool_session_allowed(db, session_id)
    try:
        session, blueprint, total_questions, profile = await diagram_blueprint_context(
            db, session_id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    question_budget = total_questions

    if async_pipeline_enabled():
        try:
            result = await submit_response_record(
                db=db,
                question_id=payload.question_id,
                session_id=session_id,
                answer_text=payload.answer_text,
                learner_id=payload.learner_id,
            )
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

        is_complete = (payload.question_index + 1) >= question_budget
        await db.commit()

        if not is_complete:
            session = await db.get(AssessmentSession, session_id)
            if session is not None:
                set_diagram_generating(
                    session,
                    total_questions=question_budget,
                    for_index=payload.question_index + 1,
                )
                await db.commit()
            schedule_diagram_post_answer(
                session_id=session_id,
                question_index=payload.question_index,
                diagram_response_id=result["response_id"],
                question_id=payload.question_id,
                answer_text=payload.answer_text,
            )
            return DiagramAnswerResponse(
                next_question=None,
                is_complete=False,
                status="generating",
                total_questions=question_budget,
            )

        return DiagramAnswerResponse(
            next_question=None,
            is_complete=True,
            status="ready",
            total_questions=question_budget,
        )

    try:
        result = await submit_response(
            db=db,
            question_id=payload.question_id,
            session_id=session_id,
            answer_text=payload.answer_text,
            learner_id=payload.learner_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    await db.flush()
    loop_result = await run_diagram_loop(
        session_id=session_id,
        question_index=payload.question_index,
        diagram_response_id=result["response_id"],
        total_questions=question_budget,
        db=db,
    )
    is_complete = loop_result["is_complete"]
    next_question: DiagramNextQuestion | None = None
    if not is_complete:
        next_plan = {
            "next_question_index": payload.question_index + 1,
            "memory_summary": loop_result.get("memory_summary", ""),
        }
        try:
            generated = await generate_and_store_next_diagram(
                db=db,
                next_plan=next_plan,
                learner_profile=profile,
                admin_config=blueprint,
            )
            next_question = _serialize_generated(generated)
        except Exception as exc:  # noqa: BLE001
            _logger.error("diagram_next_generation_failed", error=str(exc))

    await db.commit()
    return DiagramAnswerResponse(
        next_question=next_question,
        is_complete=is_complete,
        status="ready",
        total_questions=question_budget,
    )
