"""Admin authentication and assessment CRUD routes."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.admin.models import Assessment
from app.admin.schemas import (
    AdminLoginRequest,
    AssessmentCreate,
    AssessmentLinkResponse,
    AssessmentRead,
    AssessmentUpdate,
    BlueprintGenerateResponse,
    JudgeReviewListItem,
    JudgeReviewRead,
    TokenResponse,
)
from app.agent.nodes.blueprint import run_planner
from app.config import get_settings
from app.core.deps import RateLimitedRoute, get_current_admin, get_db
from app.core.security import create_access_token, credentials_exception
from app.shared.schemas.proctoring import SessionIntegritySnapshot
from app.sessions.models import AssessmentSession

router = APIRouter(tags=["admin"], route_class=RateLimitedRoute)


def _learner_name_from_profile(raw: str) -> str:
    profile = _parse_json_field(raw)
    name = profile.get("name")
    return name if isinstance(name, str) and name.strip() else "Learner"


def _parse_json_field(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _to_assessment_read(row: Assessment) -> AssessmentRead:
    return AssessmentRead(
        id=row.id,
        title=row.title,
        prompt=row.prompt,
        blueprint_json=_parse_json_field(row.blueprint_json),
        tool_config=_parse_json_field(row.tool_config),
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/api/v1/auth/token", response_model=TokenResponse)
async def admin_login(
    request: Request,
    payload: AdminLoginRequest,
) -> TokenResponse:
    settings = get_settings()
    if (
        payload.username != settings.ADMIN_USERNAME
        or payload.password != settings.ADMIN_PASSWORD.get_secret_value()
    ):
        raise credentials_exception()
    token = create_access_token({"sub": payload.username, "role": "admin"})
    return TokenResponse(access_token=token)


@router.get("/api/v1/admin/assessments", response_model=list[AssessmentRead])
async def list_assessments(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin: dict[str, Any] = Depends(get_current_admin),
) -> list[AssessmentRead]:
    stmt = select(Assessment).order_by(Assessment.created_at.desc())
    rows = (await db.exec(stmt)).all()
    return [_to_assessment_read(row) for row in rows]


@router.post(
    "/api/v1/admin/assessments",
    response_model=AssessmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_assessment(
    request: Request,
    payload: AssessmentCreate,
    db: AsyncSession = Depends(get_db),
    _admin: dict[str, Any] = Depends(get_current_admin),
) -> AssessmentRead:
    row = Assessment(
        id=str(uuid.uuid4()),
        title=payload.title,
        prompt=payload.prompt,
        blueprint_json=json.dumps(payload.blueprint_json),
        tool_config=json.dumps(payload.tool_config),
        status=payload.status,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _to_assessment_read(row)


@router.get("/api/v1/admin/assessments/{assessment_id}", response_model=AssessmentRead)
async def get_assessment(
    request: Request,
    assessment_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: dict[str, Any] = Depends(get_current_admin),
) -> AssessmentRead:
    row = await db.get(Assessment, assessment_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found",
        )
    return _to_assessment_read(row)


@router.patch(
    "/api/v1/admin/assessments/{assessment_id}",
    response_model=AssessmentRead,
)
async def update_assessment(
    request: Request,
    assessment_id: str,
    payload: AssessmentUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: dict[str, Any] = Depends(get_current_admin),
) -> AssessmentRead:
    row = await db.get(Assessment, assessment_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found",
        )
    if payload.title is not None:
        row.title = payload.title
    if payload.prompt is not None:
        row.prompt = payload.prompt
    if payload.blueprint_json is not None:
        row.blueprint_json = json.dumps(payload.blueprint_json)
    if payload.tool_config is not None:
        row.tool_config = json.dumps(payload.tool_config)
    if payload.status is not None:
        row.status = payload.status
    await db.commit()
    await db.refresh(row)
    return _to_assessment_read(row)


def _enabled_tools_from_config(tool_config: dict[str, Any]) -> list[str]:
    """Return the tool keys flagged truthy in an admin tool config.

    Args:
        tool_config: Parsed ``tool_config`` mapping, e.g. ``{"mcq": True}``.

    Returns:
        The enabled tool keys in admin vocabulary (uses ``"code"``).
    """
    return [tool for tool, enabled in tool_config.items() if bool(enabled)]


@router.post(
    "/api/v1/admin/assessments/{assessment_id}/generate-blueprint",
    response_model=BlueprintGenerateResponse,
)
async def generate_blueprint(
    request: Request,
    assessment_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: dict[str, Any] = Depends(get_current_admin),
) -> BlueprintGenerateResponse:
    """Run the planner agent and persist the generated blueprint.

    Reads the assessment's ``prompt`` and ``tool_config``, calls
    :func:`app.agent.nodes.blueprint.run_planner`, stores the structured
    blueprint on the row, and marks the assessment ``active``.

    Args:
        request: The inbound request (required by the rate-limited route class).
        assessment_id: UUID of the assessment to plan.
        db: Async database session dependency.
        _admin: Authenticated admin claims (authorization gate).

    Returns:
        The generated blueprint plus a learner shareable link.

    Raises:
        HTTPException: 404 if the assessment does not exist, 422 if no tools are
            enabled or the planner fails to produce a valid blueprint.
    """
    row = await db.get(Assessment, assessment_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found",
        )

    tools_enabled = _enabled_tools_from_config(_parse_json_field(row.tool_config))
    if not tools_enabled:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No tools enabled for this assessment",
        )

    try:
        blueprint = await run_planner(row.prompt, tools_enabled)
    except Exception as exc:  # noqa: BLE001 - surface planner failure as 422
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Blueprint generation failed: {exc}",
        ) from exc

    row.blueprint_json = blueprint.model_dump_json()
    row.status = "active"
    await db.commit()
    await db.refresh(row)

    return BlueprintGenerateResponse(
        assessment_id=row.id,
        title=blueprint.title,
        blueprint=blueprint.model_dump(),
        shareable_link=f"/assessment/{row.id}",
    )


@router.get(
    "/api/v1/admin/assessments/{assessment_id}/link",
    response_model=AssessmentLinkResponse,
)
async def get_assessment_link(
    request: Request,
    assessment_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: dict[str, Any] = Depends(get_current_admin),
) -> AssessmentLinkResponse:
    """Return the shareable learner link for a published assessment.

    Args:
        request: The inbound request (required by the rate-limited route class).
        assessment_id: UUID of the assessment.
        db: Async database session dependency.
        _admin: Authenticated admin claims (authorization gate).

    Returns:
        The shareable link, title, and status for the assessment.

    Raises:
        HTTPException: 404 if not found, 409 if the assessment is not active.
    """
    row = await db.get(Assessment, assessment_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found",
        )
    if row.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assessment is not active; generate a blueprint first",
        )
    return AssessmentLinkResponse(
        assessment_id=row.id,
        shareable_link=f"/assessment/{row.id}",
        title=row.title,
        status=row.status,
    )


@router.get(
    "/api/v1/admin/sessions/{session_id}/integrity-summary",
    response_model=SessionIntegritySnapshot,
)
async def get_session_integrity_summary(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: dict[str, Any] = Depends(get_current_admin),
) -> SessionIntegritySnapshot:
    """Integrity snapshot for Abutaleb's admin results panel (radar + integrity)."""
    from app.proctoring.enforcement import get_integrity_snapshot_for_admin

    return await get_integrity_snapshot_for_admin(db, session_id)


@router.get(
    "/api/v1/admin/sessions/pending-review",
    response_model=list[JudgeReviewListItem],
)
async def list_pending_judge_reviews(
    request: Request,
    assessment_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    _admin: dict[str, Any] = Depends(get_current_admin),
) -> list[JudgeReviewListItem]:
    """List sessions awaiting admin approval of judge/grading results."""
    stmt = select(AssessmentSession).where(
        AssessmentSession.status == "pending_review",
    )
    if assessment_id:
        stmt = stmt.where(AssessmentSession.assessment_id == assessment_id)
    stmt = stmt.order_by(AssessmentSession.completed_at.desc())
    rows = (await db.exec(stmt)).all()
    items: list[JudgeReviewListItem] = []
    for row in rows:
        reason = None
        if row.judge_review_json:
            try:
                from app.agent.nodes.judge import judge_result_from_json

                review = judge_result_from_json(row.judge_review_json)
                reason = review.review_reason
            except (ValueError, json.JSONDecodeError):
                reason = "Judge review data unavailable"
        items.append(
            JudgeReviewListItem(
                session_id=row.id,
                assessment_id=row.assessment_id,
                learner_name=_learner_name_from_profile(row.learner_profile_json),
                review_reason=reason,
                completed_at=row.completed_at,
            )
        )
    return items


@router.get(
    "/api/v1/admin/sessions/{session_id}/judge-review",
    response_model=JudgeReviewRead,
)
async def get_judge_review(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: dict[str, Any] = Depends(get_current_admin),
) -> JudgeReviewRead:
    """Return the held judge review payload for admin inspection."""
    from app.agent.nodes.judge import judge_result_from_json

    session = await db.get(AssessmentSession, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    if session.status != "pending_review" or not session.judge_review_json:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Session is not awaiting judge review",
        )
    review = judge_result_from_json(session.judge_review_json)
    return JudgeReviewRead(
        session_id=session.id,
        assessment_id=session.assessment_id,
        learner_name=_learner_name_from_profile(session.learner_profile_json),
        status=session.status,
        review_status=review.review_status,
        review_reason=review.review_reason,
        llm_judge_score=review.llm_judge_score,
        narrative=review.narrative,
        grade_result_count=review.grade_result_count,
    )


@router.post(
    "/api/v1/admin/sessions/{session_id}/judge-review/approve",
    response_model=JudgeReviewRead,
)
async def approve_judge_review(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: dict[str, Any] = Depends(get_current_admin),
) -> JudgeReviewRead:
    """Approve held judge results, finalize grading, and release report/email."""
    from app.agent.nodes.judge import approve_pending_judge_review
    from app.workers.email_tasks import schedule_finalize_after_judge_approval

    session = await db.get(AssessmentSession, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    try:
        review = await approve_pending_judge_review(db, session)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    await db.commit()

    profile = _parse_json_field(session.learner_profile_json)
    learner_email = profile.get("email")
    email = (
        learner_email
        if isinstance(learner_email, str) and learner_email.strip()
        else None
    )
    schedule_finalize_after_judge_approval(session.id, learner_email=email)

    return JudgeReviewRead(
        session_id=session.id,
        assessment_id=session.assessment_id,
        learner_name=_learner_name_from_profile(session.learner_profile_json),
        status=session.status,
        review_status=review.review_status,
        review_reason=review.review_reason,
        llm_judge_score=review.llm_judge_score,
        narrative=review.narrative,
        grade_result_count=review.grade_result_count,
    )
