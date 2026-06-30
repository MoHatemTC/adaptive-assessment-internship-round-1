"""Learner session sign-in and lifecycle routes."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from pydantic import ValidationError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.admin.models import Assessment
from app.agent.graph import run_examiner_turn
from app.core.deps import (
    RateLimitedRoute,
    get_current_admin,
    get_db,
    get_session_by_token,
)
from app.core.logging import get_logger
from app.core.security import generate_session_token, hash_token
from app.proctoring import service as proctoring_service
from app.proctoring.deps import require_active_proctored_session
from app.sessions.models import AssessmentSession
from app.sessions.schemas import (
    ExaminerRespondRequest,
    ExaminerRespondResponse,
    LearnerProfile,
    SessionListItem,
    SessionRead,
    SessionSignInResponse,
)
from app.sessions.time_enforcement import (
    apply_session_deadline,
    load_blueprint_for_session,
)
from app.shared.cv_parser import extract_cv_context
from app.shared.schemas.proctoring import ProctoringPolicyResponse
from app.workers.email_tasks import schedule_post_completion_pipeline

_logger = get_logger(__name__)

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
    assessment_id: str = Form(...),
    learner_profile: str = Form(...),
    cv_file: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
) -> SessionSignInResponse:
    """Create a pending learner session, optionally enriched from a CV PDF.

    Accepts ``multipart/form-data`` so an optional PDF CV can ride alongside the
    learner profile. When a PDF is supplied it is parsed into structured context
    and merged into the stored profile under ``cv_context``. CV parsing is
    best-effort: a failed or empty parse simply omits ``cv_context`` and never
    blocks sign-in.

    Args:
        request: The inbound request (required by the rate-limited route class).
        assessment_id: Target assessment UUID (multipart form field).
        learner_profile: JSON string of the learner profile (multipart form field).
        cv_file: Optional uploaded PDF CV.
        db: Async database session dependency.

    Returns:
        The new session id and its bearer access token.

    Raises:
        HTTPException: 404 if the assessment is missing or inactive; 422 if the
            ``learner_profile`` JSON is invalid.
    """
    assessment = await db.get(Assessment, assessment_id)
    if assessment is None or assessment.status != "active":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found or not active",
        )

    try:
        profile = LearnerProfile.model_validate_json(learner_profile)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid learner_profile payload",
        ) from exc

    cv_context: dict = {}
    if cv_file is not None:
        filename = (cv_file.filename or "").lower()
        is_pdf = cv_file.content_type == "application/pdf" or filename.endswith(".pdf")
        if is_pdf:
            pdf_bytes = await cv_file.read()
            cv_context = await extract_cv_context(pdf_bytes)

    profile_data = profile.model_dump()
    if cv_context:
        profile_data["cv_context"] = cv_context
    learner_profile_json = json.dumps(profile_data)

    raw_token = generate_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=_SESSION_TTL_HOURS)
    row = AssessmentSession(
        assessment_id=assessment_id,
        learner_profile_json=learner_profile_json,
        status="pending",
        token_hash=hash_token(raw_token),
        expires_at=expires_at,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return SessionSignInResponse(session_id=row.id, access_token=raw_token)


@router.get("", response_model=list[SessionListItem])
async def list_sessions(
    request: Request,
    assessment_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: dict[str, Any] = Depends(get_current_admin),
) -> list[SessionListItem]:
    """List completed sessions for an assessment (admin only).

    Returns only non-sensitive fields for building a session picker. Scores,
    grading, and memory data are never exposed here — admins reach those via
    the dedicated report endpoint.

    Args:
        request: The inbound request (required by the rate-limited route class).
        assessment_id: Assessment UUID to filter sessions by (query parameter).
        db: Async database session dependency.
        _admin: Authenticated admin claims (authorization gate).

    Returns:
        Completed sessions for the assessment, newest first: id, status,
        created_at, and the learner's display name.
    """
    stmt = (
        select(AssessmentSession)
        .where(
            AssessmentSession.assessment_id == assessment_id,
            AssessmentSession.status == "completed",
        )
        .order_by(AssessmentSession.completed_at.desc())
    )
    rows = (await db.exec(stmt)).all()
    return [
        SessionListItem(
            id=row.id,
            status=row.status,
            created_at=row.created_at,
            learner_name=_parse_profile(row.learner_profile_json).get("name")
            or "Learner",
        )
        for row in rows
    ]


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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Session mismatch"
        )
    if session.status not in {"pending", "active"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Session not startable"
        )
    session.status = "active"
    if session.started_at is None:
        session.started_at = datetime.now(timezone.utc)
    blueprint = await load_blueprint_for_session(db, session)
    apply_session_deadline(session, blueprint)
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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Session mismatch"
        )
    if session.status == "completed":
        return await _to_session_read(db, session)
    await proctoring_service.stop_proctoring_session(db, session.id)
    session.status = "completed"
    session.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(session)

    # Trigger post-completion pipeline: judge → report → email.
    try:
        profile = _parse_profile(session.learner_profile_json)
        learner_email = profile.get("email") or None
    except Exception:  # noqa: BLE001
        learner_email = None
    schedule_post_completion_pipeline(
        session_id=session.id,
        learner_email=learner_email,
    )

    return await _to_session_read(db, session)


@router.post("/{session_id}/respond", response_model=ExaminerRespondResponse)
async def respond(
    request: Request,
    session_id: str,
    payload: ExaminerRespondRequest,
    db: AsyncSession = Depends(get_db),
    session: AssessmentSession = Depends(require_active_proctored_session),
) -> ExaminerRespondResponse:
    """Advance the examiner and report which tool the learner should use next.

    The examiner is routing-only: the answer itself is graded by the tool's own
    endpoint. This endpoint settles the just-completed question and returns the
    next tool to render. The response is learner-safe and never includes scores,
    correctness, grading feedback, or memory details.

    Args:
        request: The inbound request (required by the rate-limited route class).
        session_id: Platform assessment session UUID from the path.
        payload: The tool that acted and the advance action.
        db: Async database session dependency.
        session: The token-authenticated session.

    Returns:
        The current tool, a render hint for it, and the completion flag.

    Raises:
        HTTPException: 403 on session mismatch, 422 if the assessment has no
            valid blueprint.
    """
    if session.id != session_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Session mismatch"
        )

    try:
        result = await run_examiner_turn(
            session_id=session_id,
            tool=payload.tool,
            action=payload.action,
            db=db,
        )
    except ValueError as exc:
        _logger.warning("examiner_turn_failed", session_id=session_id, reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return ExaminerRespondResponse(
        current_tool=result["current_tool"],
        next_tool_info=result["next_tool_info"],
        is_complete=result["is_complete"],
    )
