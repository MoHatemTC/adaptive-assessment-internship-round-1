"""FastAPI routes for the MCQ feature.

Exposes endpoints to create a question, fetch a question without its answer,
submit an answer silently, and run the adaptive MCQ loop.

Submission is silent:
- correctness is not returned
- score is not returned
- correct_option is never exposed to the learner
"""

from typing import Dict

from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.deps import get_db
from app.features.mcq.loop import run_mcq_adaptive_loop
from app.features.mcq.schemas import (
    MCQAdaptiveSubmitRequest,
    MCQAdaptiveSubmitResponse,
    MCQCreateRequest,
    MCQQuestionResponse,
    MCQSubmitRequest,
    MCQSubmitResponse,
)
from app.features.mcq.service import (
    build_submit_response,
    create_question,
    get_question,
)

router = APIRouter(prefix="/mcq", tags=["mcq"])


@router.get("/health")
def mcq_health_check() -> Dict[str, str]:
    """Report that the MCQ feature is ready."""
    return {
        "status": "ready",
        "feature": "mcq",
    }


@router.post("/questions", response_model=MCQQuestionResponse)
async def create_mcq_question(
    payload: MCQCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, object]:
    """Create an MCQ question and return it without the correct answer."""
    return await create_question(
        db=db,
        question_text=payload.question_text,
        correct_option=payload.correct_option,
        options=[
            {"label": option.label, "text": option.text}
            for option in payload.options
        ],
        difficulty=payload.difficulty,
        dimension=payload.dimension,
    )


@router.get("/questions/{question_id}", response_model=MCQQuestionResponse)
async def get_mcq_question(
    question_id: int,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, object]:
    """Return an MCQ question without exposing the correct answer."""
    return await get_question(db=db, question_id=question_id)


@router.post("/submit", response_model=MCQSubmitResponse)
async def submit_mcq_answer(
    payload: MCQSubmitRequest,
    db: AsyncSession = Depends(get_db),
) -> MCQSubmitResponse:
    """Submit, silently grade, and persist an MCQ answer."""
    await build_submit_response(
        db=db,
        question_id=payload.question_id,
        selected_option=payload.selected_option,
        session_id=payload.session_id,
        question_index=payload.question_index,
    )

    return MCQSubmitResponse(received=True, question_id=payload.question_id)


@router.post("/adaptive-submit", response_model=MCQAdaptiveSubmitResponse)
async def adaptive_submit_mcq_answer(
    payload: MCQAdaptiveSubmitRequest,
    db: AsyncSession = Depends(get_db),
) -> MCQAdaptiveSubmitResponse:
    """Submit an answer and return the next adaptive MCQ."""
    result = await run_mcq_adaptive_loop(
        db=db,
        question_id=payload.question_id,
        selected_option=payload.selected_option,
        session_id=payload.session_id,
        question_index=payload.question_index,
        learner_profile=payload.learner_profile,
        admin_config=payload.admin_config,
    )

    return MCQAdaptiveSubmitResponse(
        received=result["received"],
        question_id=result["question_id"],
        next_plan=result["next_plan"],
        next_question=result["next_question"],
    )
