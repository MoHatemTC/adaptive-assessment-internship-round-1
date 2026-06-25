"""FastAPI routes for the SVG diagram feature."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.deps import get_db
from app.core.logging import get_logger
from app.features.diagram.llm_generation import generate_and_store_next_diagram
from app.features.diagram.loop import run_diagram_loop
from app.features.diagram.schemas import (
    DiagramAnswerRequest,
    DiagramAnswerResponse,
    DiagramCreateRequest,
    DiagramNextQuestion,
    DiagramQuestionResponse,
)
from app.features.diagram.service import create_question, get_question, submit_response

_logger = get_logger(__name__)

router = APIRouter(prefix="/diagram", tags=["diagram"])


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


@router.post(
    "/sessions/{session_id}/answer",
    response_model=DiagramAnswerResponse,
)
async def submit_adaptive_diagram_answer(
    session_id: str,
    payload: DiagramAnswerRequest,
    db: AsyncSession = Depends(get_db),
) -> DiagramAnswerResponse:
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
        total_questions=payload.total_questions,
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
                learner_profile=payload.learner_profile,
                admin_config=payload.admin_config,
            )
            next_question = DiagramNextQuestion(
                id=generated["id"],
                svg_content=generated["svg_content"],
                prompt=generated["prompt"],
                difficulty=generated["difficulty"],
                dimension=generated.get("dimension"),
            )
        except Exception as exc:  # noqa: BLE001 - generation must not break session
            _logger.error("diagram_next_generation_failed", error=str(exc))
            next_question = None

    await db.commit()
    return DiagramAnswerResponse(next_question=next_question, is_complete=is_complete)
