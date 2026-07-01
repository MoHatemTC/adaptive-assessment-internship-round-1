"""Pydantic schemas for admin assessment management."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AssessmentCreate(BaseModel):
    title: str
    prompt: str
    blueprint_json: dict[str, Any] = Field(default_factory=dict)
    tool_config: dict[str, Any] = Field(default_factory=dict)
    status: str = "draft"


class AssessmentUpdate(BaseModel):
    title: str | None = None
    prompt: str | None = None
    blueprint_json: dict[str, Any] | None = None
    tool_config: dict[str, Any] | None = None
    status: str | None = None


class AssessmentRead(BaseModel):
    id: str
    title: str
    prompt: str
    blueprint_json: dict[str, Any]
    tool_config: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BlueprintGenerateResponse(BaseModel):
    """Admin-facing result of generating a blueprint for an assessment."""

    assessment_id: str
    title: str
    blueprint: dict[str, Any]
    shareable_link: str


class AssessmentLinkResponse(BaseModel):
    """Shareable link payload for a published (active) assessment."""

    assessment_id: str
    shareable_link: str
    title: str
    status: str


class JudgeReviewRead(BaseModel):
    """Admin-facing snapshot of a session held for judge review."""

    session_id: str
    assessment_id: str
    learner_name: str
    status: str
    review_status: str
    review_reason: str | None = None
    llm_judge_score: float | None = None
    narrative: str = ""
    grade_result_count: int = 0


class JudgeReviewListItem(BaseModel):
    session_id: str
    assessment_id: str
    learner_name: str
    review_reason: str | None = None
    completed_at: datetime | None = None
