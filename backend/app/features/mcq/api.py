from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.deps import get_db
from app.features.mcq.schemas import (
    MCQGenerateRequest,
    MCQQuestionResponse,
    MCQSubmitRequest,
    MCQSubmitResponse,
)
from app.features.mcq.service import build_sample_question, build_submit_response

router = APIRouter(prefix="/mcq", tags=["MCQ"])


@router.get("/health")
def mcq_health_check():
    return {
        "status": "ready",
        "feature": "mcq",
    }


@router.post("/generate", response_model=MCQQuestionResponse)
async def generate_mcq_question(
    payload: MCQGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate or return an MCQ question from PostgreSQL.
    """
    return await build_sample_question(
        db=db,
        topic=payload.topic,
        difficulty=payload.difficulty,
        question_count=payload.question_count,
    )


@router.get("/question", response_model=MCQQuestionResponse)
async def get_mcq_question(
    db: AsyncSession = Depends(get_db),
):
    """
    Return an MCQ question without exposing the correct answer.
    """
    return await build_sample_question(db=db)


@router.post("/submit", response_model=MCQSubmitResponse)
async def submit_mcq_answer(
    payload: MCQSubmitRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit, silently grade, and persist an MCQ answer in PostgreSQL.
    """
    return await build_submit_response(
        db=db,
        question_id=payload.question_id,
        selected_option=payload.selected_option,
        learner_id=payload.learner_id,
    )