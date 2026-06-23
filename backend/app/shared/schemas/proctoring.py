"""Shared Pydantic types for the proctoring and integrity system.

Frontend (Mohamed) and future report modules import from here. No divergent
shapes — all proctoring contracts live in this module.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ProctoringEventType = Literal[
    "tab_switch",
    "copy_paste",
    "screenshot",
    "ai_usage",
    "identity_fail",
    "identity_verified",
]

ProctoringSeverity = Literal["low", "medium", "high"]

VerificationStatus = Literal["pending", "verified", "flagged", "identity_failed"]


class ProctoringPolicy(BaseModel):
    """Per-assessment integrity policy resolved from admin configuration.

    Attributes:
        high_severity_threshold: Number of high-severity events that auto-flags
            the session.
    """

    high_severity_threshold: int = Field(ge=1)


class ProctoringEventCreate(BaseModel):
    """Payload to record a new integrity event."""

    session_id: str = Field(min_length=1, max_length=36)
    event_type: ProctoringEventType
    severity: ProctoringSeverity
    metadata: Optional[dict[str, Any]] = None
    client_timestamp: Optional[datetime] = None


class ProctoringEventRead(BaseModel):
    """Persisted integrity event returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    event_type: ProctoringEventType
    severity: ProctoringSeverity
    metadata: Optional[dict[str, Any]] = None
    client_timestamp: Optional[datetime] = None
    created_at: datetime


class IdentityVerifyRequest(BaseModel):
    """Face-match identity verification at session start.

    Images are processed in memory only and never persisted as blobs.
    """

    session_id: str = Field(min_length=1, max_length=36)
    reference_image_b64: str = Field(min_length=1)
    live_capture_b64: str = Field(min_length=1)


class IdentityVerifyResponse(BaseModel):
    """Result of server-side identity verification."""

    verified: bool
    match_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    verification_status: VerificationStatus
    message: Optional[str] = None


class SessionIntegritySummary(BaseModel):
    """Published contract for session integrity — consumed by FE and reports."""

    session_id: str
    verification_status: VerificationStatus
    high_severity_count: int = Field(ge=0)
    threshold: int = Field(ge=1)
    identity_verified: bool
    events: list[ProctoringEventRead]
