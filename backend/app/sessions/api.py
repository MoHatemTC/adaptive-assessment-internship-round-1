"""Learner session sign-in and lifecycle routes."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.admin.models import Assessment
from app.core.deps import RateLimitedRoute, get_db, get_session_by_token
from app.core.security import generate_session_token, hash_token
from app.proctoring import service as proctoring_service
from app.shared.schemas.proctoring import ProctoringPolicyResponse
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


async def _to_session_read(
    db: AsyncSession,
    row: AssessmentSession,
    *,
    proctoring_policy: ProctoringPolicyResponse | None = None,
) -> SessionRead:
    integrity = await proctoring_service.get_integrity_snapshot(db, row.id)
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
        proctoring_status=row.proctoring_status,
        integrity=integrity,
        proctoring_policy=proctoring_policy,
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
    db: AsyncSession = Depends(get_db),
) -> SessionRead:
    return await _to_session_read(db, session)


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
    assessment = await db.get(Assessment, session.assessment_id)
    assessment_type = None
    if assessment is not None:
        tool_config = json.loads(assessment.tool_config or "{}")
        if isinstance(tool_config, dict):
            for key in ("coding", "voice", "mcq", "diagram"):
                if tool_config.get(key):
                    assessment_type = key
                    break
    proctoring_policy = await proctoring_service.start_proctoring_session(
        db,
        session.id,
        assessment_type=assessment_type,
    )
    await db.commit()
    await db.refresh(session)
    return await _to_session_read(db, session, proctoring_policy=proctoring_policy)


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
        return await _to_session_read(db, session)
    await proctoring_service.stop_proctoring_session(db, session.id)
    session.status = "completed"
    session.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(session)
    return await _to_session_read(db, session)
