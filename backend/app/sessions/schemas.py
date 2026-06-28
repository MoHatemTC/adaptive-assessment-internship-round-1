"""Pydantic schemas for learner session lifecycle."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.shared.schemas.proctoring import (
    ProctoringPolicyResponse,
    SessionIntegritySnapshot,
)


class LearnerProfile(BaseModel):
    name: str = ""
    role: str = ""
    level: str = ""
    target_skills: list[str] = Field(default_factory=list)
    consent_given: bool = False
    cv_context: dict = Field(default_factory=dict)
    # Populated by the backend after CV parsing; never sent by the frontend.


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
    proctoring_status: str = "not_started"
    integrity: SessionIntegritySnapshot | None = None
    proctoring_policy: ProctoringPolicyResponse | None = None


class ExaminerRespondRequest(BaseModel):
    """Learner turn signal for the examiner router.

    Carries no answer data — the tool's own endpoint grades the answer. This only
    tells the examiner which tool acted and how to advance.
    """

    tool: str
    action: str = "next"  # "start" | "next" | "complete_tool"


class ExaminerRespondResponse(BaseModel):
    """Learner-safe examiner routing result. Never contains scores or grading."""

    current_tool: str | None = None
    next_tool_info: dict[str, Any] | None = None
    is_complete: bool


class SessionListItem(BaseModel):
    """One row of an admin's completed-session listing for an assessment.

    Deliberately excludes scores, grading, and memory data — admins reach
    those via the dedicated report endpoint, not the listing.
    """

    id: str
    status: str
    created_at: datetime
    learner_name: str
