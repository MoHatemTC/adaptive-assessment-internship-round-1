"""
api.py — FastAPI router for the diagram feature.

Routes:
  GET  /diagram/{question_id}         → DiagramQuestionResponse
  POST /diagram/{question_id}/answer  → DiagramAnswerResponse

The router is registered in the main app with prefix="/diagram".
Both routes are used by the agent (tool.py) and the frontend (DiagramView.tsx).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.features.diagram.schemas import (
    DiagramQuestionResponse,
    DiagramAnswerRequest,
    DiagramAnswerResponse,
)
from app.features.diagram.service import DiagramService

router = APIRouter(prefix="/diagram", tags=["diagram"])
_service = DiagramService()


@router.get(
    "/{question_id}",
    response_model=DiagramQuestionResponse,
    summary="Fetch a diagram question (image URL + prompt + difficulty)",
)
async def get_diagram_question(
    question_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> DiagramQuestionResponse:
    """
    Returns the diagram item for the learner:
      - served/signed image_url  (ready for <img> in DiagramView.tsx)
      - prompt                   (the question to answer)
      - difficulty + dimension   (used by agent for adaptation)

    Rubric is NOT included — it stays server-side for silent grading.
    """
    question = await _service.fetch_question(db, question_id)
    if question is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Diagram question {question_id} not found",
        )
    return DiagramQuestionResponse.model_validate(question)


@router.post(
    "/{question_id}/answer",
    response_model=DiagramAnswerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a learner text answer — persisted and graded silently",
)
async def submit_diagram_answer(
    question_id: uuid.UUID,
    body: DiagramAnswerRequest,
    db: AsyncSession = Depends(get_db),
) -> DiagramAnswerResponse:
    """
    Accepts the learner's text answer, persists it as a DiagramAnswer record
    (queryable by session_id), then grades it silently using the vision model.

    Returns a structured grading result to the agent.
    Score and feedback are NEVER forwarded to the learner mid-session.
    """
    try:
        answer = await _service.submit_answer(
            db=db,
            question_id=question_id,
            session_id=body.session_id,
            answer_text=body.answer_text,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    await db.commit()

    question = await _service.fetch_question(db, question_id)

    return DiagramAnswerResponse(
        answer_id=answer.id,
        session_id=answer.session_id,
        question_id=answer.question_id,
        score=answer.score,
        dimension=question.dimension,
        grading_feedback=answer.grading_feedback,
        graded_at=answer.graded_at,
    )