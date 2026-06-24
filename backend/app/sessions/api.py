"""Learner session sign-in and lifecycle routes."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.admin.models import Assessment
from app.core.deps import RateLimitedRoute, get_db, get_session_by_token
from app.core.security import generate_session_token, hash_token
from app.sessions.models import AssessmentSession
from app.sessions.schemas import (
    SessionRead,
    SessionSignInRequest,
    SessionSignInResponse,
)

router = APIRouter(
    prefix="/api/v1/sessions",
    tags=["sessions"],
    route_class=RateLimitedRoute,
)

_SESSION_TTL_HOURS = 24


def _parse_profile(raw: str) -> dict:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _to_session_read(row: AssessmentSession) -> SessionRead:
    return SessionRead(
        id=row.id,
        assessment_id=row.assessment_id,
        learner_profile=_parse_profile(row.learner_profile_json),
        status=row.status,
        code_session_id=row.code_session_id,
        started_at=row.started_at,
        completed_at=row.completed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/sign-in", response_model=SessionSignInResponse, status_code=201)
async def sign_in(
    request: Request,
    payload: SessionSignInRequest,
    db: AsyncSession = Depends(get_db),
) -> SessionSignInResponse:
    assessment = await db.get(Assessment, payload.assessment_id)
    if assessment is None or assessment.status != "active":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found or not active",
        )
    raw_token = generate_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=_SESSION_TTL_HOURS)
    row = AssessmentSession(
        assessment_id=payload.assessment_id,
        learner_profile_json=payload.learner_profile.model_dump_json(),
        status="pending",
        token_hash=hash_token(raw_token),
        expires_at=expires_at,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return SessionSignInResponse(session_id=row.id, access_token=raw_token)


@router.get("/me", response_model=SessionRead)
async def get_my_session(
    request: Request,
    session: AssessmentSession = Depends(get_session_by_token),
) -> SessionRead:
    return _to_session_read(session)


@router.post("/{session_id}/start", response_model=SessionRead)
async def start_session(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db),
    session: AssessmentSession = Depends(get_session_by_token),
) -> SessionRead:
    if session.id != session_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session mismatch")
    if session.status not in {"pending", "active"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session not startable")
    session.status = "active"
    if session.started_at is None:
        session.started_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(session)
    return _to_session_read(session)


@router.post("/{session_id}/complete", response_model=SessionRead)
async def complete_session(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db),
    session: AssessmentSession = Depends(get_session_by_token),
) -> SessionRead:
    if session.id != session_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session mismatch")
    if session.status == "completed":
        return _to_session_read(session)
    session.status = "completed"
    session.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(session)
    return _to_session_read(session)
