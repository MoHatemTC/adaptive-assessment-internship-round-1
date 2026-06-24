"""Admin authentication and assessment CRUD routes."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.admin.models import Assessment
from app.admin.schemas import AssessmentCreate, AssessmentRead, AssessmentUpdate, TokenResponse
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
    form: OAuth2PasswordRequestForm = Depends(),
) -> TokenResponse:
    settings = get_settings()
    if (
        form.username != settings.ADMIN_USERNAME
        or form.password != settings.ADMIN_PASSWORD.get_secret_value()
    ):
        raise credentials_exception()
    token = create_access_token({"sub": form.username, "role": "admin"})
    return TokenResponse(access_token=token)


@router.get("/api/v1/admin/assessments", response_model=list[AssessmentRead])
async def list_assessments(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin: dict[str, Any] = Depends(get_current_admin),
) -> list[AssessmentRead]:
    rows = (await db.exec(select(Assessment).order_by(Assessment.created_at.desc()))).all()
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    return _to_assessment_read(row)


@router.patch("/api/v1/admin/assessments/{assessment_id}", response_model=AssessmentRead)
async def update_assessment(
    request: Request,
    assessment_id: str,
    payload: AssessmentUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: dict[str, Any] = Depends(get_current_admin),
) -> AssessmentRead:
    row = await db.get(Assessment, assessment_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
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
