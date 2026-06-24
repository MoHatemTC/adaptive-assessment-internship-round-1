"""Pydantic schemas for admin assessment management."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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
