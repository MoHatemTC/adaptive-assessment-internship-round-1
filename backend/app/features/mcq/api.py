"""FastAPI routes for the MCQ feature.

Exposes three endpoints — create a question, fetch a question (without its
answer), and submit an answer. Submission is silent: the response only
acknowledges receipt and never reveals correctness or score. The router is
named ``router`` so the application factory's auto-discovery registers it.
"""

from typing import Dict

from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.deps import get_db
from app.features.mcq.schemas import (
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
    """Report that the MCQ feature is ready.

    Returns:
        A small status payload identifying the feature.
    """
    return {
        "status": "ready",
        "feature": "mcq",
    }


@router.post("/questions", response_model=MCQQuestionResponse)
async def create_mcq_question(
    payload: MCQCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, object]:
    """Create an MCQ question and return it without the correct answer.

    Args:
        payload: Question text, difficulty, correct option, and options.
        db: Async database session dependency.

    Returns:
        The created question serialized without ``correct_option``.
    """
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
    """Return an MCQ question without exposing the correct answer.

    Args:
        question_id: Primary key of the question to fetch.
        db: Async database session dependency.

    Returns:
        The question serialized without ``correct_option``.

    Raises:
        HTTPException: 404 if the question does not exist.
    """
    return await get_question(db=db, question_id=question_id)


@router.post("/submit", response_model=MCQSubmitResponse)
async def submit_mcq_answer(
    payload: MCQSubmitRequest,
    db: AsyncSession = Depends(get_db),
) -> MCQSubmitResponse:
    """Submit, silently grade, and persist an MCQ answer.

    Grading is silent: the response only acknowledges receipt. Correctness and
    score are persisted server-side but never returned to the learner.

    Args:
        payload: Question id, session id, selected option, and optional learner.
        db: Async database session dependency.

    Returns:
        A silent acknowledgement carrying only ``received`` and ``question_id``.

    Raises:
        HTTPException: 404 if the question does not exist.
    """
    await build_submit_response(
        db=db,
        question_id=payload.question_id,
        selected_option=payload.selected_option,
        session_id=payload.session_id,
        learner_id=payload.learner_id,
    )
    return MCQSubmitResponse(received=True, question_id=payload.question_id)
