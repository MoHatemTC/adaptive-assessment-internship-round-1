"""Pydantic schemas for learner session lifecycle."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LearnerProfile(BaseModel):
    name: str = ""
    role: str = ""
    level: str = ""
    target_skills: list[str] = Field(default_factory=list)
    consent_given: bool = False


class SessionSignInRequest(BaseModel):
    assessment_id: str
    learner_profile: LearnerProfile


class SessionSignInResponse(BaseModel):
    session_id: str
    access_token: str
    token_type: str = "bearer"


class SessionRead(BaseModel):
    id: str
    assessment_id: str
    learner_profile: dict[str, Any]
    status: str
    code_session_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
