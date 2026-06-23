"""FastAPI routes for the proctoring and integrity system."""

from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.deps import RateLimitedRoute, get_db
from app.proctoring import service
from app.proctoring.identity import FaceMatchProvider, get_face_match_provider
from app.shared.schemas.proctoring import (
    IdentityVerifyRequest,
    IdentityVerifyResponse,
    ProctoringEventCreate,
    ProctoringEventRead,
    SessionIntegritySummary,
)

router = APIRouter(
    prefix="/api/v1/proctoring",
    tags=["proctoring"],
    route_class=RateLimitedRoute,
)


def _face_provider() -> FaceMatchProvider:
    return get_face_match_provider()


@router.get("/health")
def proctoring_health_check(request: Request) -> Dict[str, str]:
    """Report that the proctoring feature is ready."""
    return {"status": "ready", "feature": "proctoring"}


@router.post("/events", response_model=ProctoringEventRead, status_code=201)
async def record_proctoring_event(
    request: Request,
    payload: ProctoringEventCreate,
    db: AsyncSession = Depends(get_db),
) -> ProctoringEventRead:
    """Record an integrity event from the frontend monitor."""
    return await service.record_event(db, payload)


@router.get(
    "/sessions/{session_id}/events",
    response_model=list[ProctoringEventRead],
)
async def list_session_events(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[ProctoringEventRead]:
    """List all integrity events for a session."""
    return await service.get_session_events(db, session_id)


@router.get(
    "/sessions/{session_id}/integrity",
    response_model=SessionIntegritySummary,
)
async def get_session_integrity(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> SessionIntegritySummary:
    """Return verification status and events for a session."""
    return await service.get_session_integrity(db, session_id)


@router.post(
    "/sessions/{session_id}/verify-identity",
    response_model=IdentityVerifyResponse,
)
async def verify_session_identity(
    request: Request,
    session_id: str,
    body: IdentityVerifyRequest,
    db: AsyncSession = Depends(get_db),
    face_provider: FaceMatchProvider = Depends(_face_provider),
) -> IdentityVerifyResponse:
    """Verify learner identity with a face match before assessment start."""
    if body.session_id != session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id in body must match path",
        )
    return await service.verify_identity(db, body, face_provider)
