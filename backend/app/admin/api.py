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
    TokenResponse,
)
from app.agent.nodes.blueprint import run_planner
from app.config import get_settings
from app.core.deps import RateLimitedRoute, get_current_admin, get_db
from app.core.security import create_access_token, credentials_exception

router = APIRouter(tags=["admin"], route_class=RateLimitedRoute)


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
