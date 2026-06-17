"""
app/features/adaptation/api.py
Shared route — not under any single feature. Register with
app.include_router(adaptation_router) in main.py.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.features.adaptation.schemas import AdaptationInput, AdaptationResult
from app.features.adaptation.repository import fetch_all_answers
from app.features.adaptation.agent import run_adaptation

router = APIRouter(prefix="/adaptation", tags=["adaptation"])


@router.post("/adapt", response_model=AdaptationResult)
async def adapt(
    body: AdaptationInput,
    db: AsyncSession = Depends(get_db),
) -> AdaptationResult:
    """
    Called by the examiner agent after ANY tool's answer (diagram, mcq,
    voice, code). Gathers normalized answers across all tools used so
    far in the session, scores 5 dimensions, returns next_difficulty.
    """
    answers = await fetch_all_answers(db, body.session_id)
    try:
        return await run_adaptation(body.session_id, answers)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))