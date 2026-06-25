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
    "window_blur",
    "fullscreen_exit",
    "devtools_open",
    "context_menu",
    "print_attempt",
    "copy",
    "paste",
    "copy_paste",
    "screenshot",
    "ai_usage",
    "idle_timeout",
    "identity_fail",
    "identity_verified",
    "face_absent",
    "multiple_faces",
    "camera_obstructed",
    "camera_disabled",
    "looking_away",
    "identity_mismatch",
    "microphone_muted",
    "microphone_disabled",
    "audio_absent",
]

ProctoringSeverity = Literal["low", "medium", "high"]

VerificationStatus = Literal["pending", "verified", "flagged", "identity_failed"]


class ProctoringPolicy(BaseModel):
    """Per-assessment integrity policy resolved from admin configuration.

    Attributes:
        high_severity_threshold: Number of high-severity events that auto-flags
            the session.
        enabled_checks: Event types the monitor should enforce for this session.
        camera_poll_interval_seconds: Recommended interval for camera frame analysis.
        event_cooldown_seconds: Minimum gap before the same event type is recorded again.
        require_camera: Whether camera consent and monitoring are expected.
        require_microphone: Whether microphone monitoring is expected (e.g. voice tool).
    """

    high_severity_threshold: int = Field(ge=1, default=3)
    enabled_checks: list[ProctoringEventType] = Field(default_factory=list)
    camera_poll_interval_seconds: int = Field(ge=5, le=120, default=20)
    event_cooldown_seconds: int = Field(ge=0, le=300, default=30)
    require_camera: bool = True
    require_microphone: bool = False


class ProctoringPolicyResponse(ProctoringPolicy):
    """Policy plus defaults for frontend integrity monitors."""

    session_id: str
    default_severities: dict[ProctoringEventType, ProctoringSeverity]


class ProctoringEventCreate(BaseModel):
    """Payload to record a new integrity event."""

    session_id: str = Field(min_length=1, max_length=36)
    event_type: ProctoringEventType
    severity: Optional[ProctoringSeverity] = None
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


class ProctoringEventBatchCreate(BaseModel):
    """Batch of integrity events from the browser monitor."""

    session_id: str = Field(min_length=1, max_length=36)
    events: list[ProctoringEventCreate] = Field(min_length=1, max_length=50)


class ProctoringEventBatchResponse(BaseModel):
    """Result of a batch integrity ingest."""

    recorded: list[ProctoringEventRead]
    skipped: list[dict[str, Any]] = Field(default_factory=list)


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


class CameraAnalyzeRequest(BaseModel):
    """Live webcam frame analysis during an assessment session.

    Images are processed in memory only and never persisted as blobs.
    """

    session_id: str = Field(min_length=1, max_length=36)
    frame_b64: str = Field(min_length=1)
    reference_image_b64: Optional[str] = None
    client_timestamp: Optional[datetime] = None


class CameraViolationRead(BaseModel):
    """A single integrity violation detected in a camera frame."""

    event_type: ProctoringEventType
    severity: ProctoringSeverity
    description: str


class CameraAnalyzeResponse(BaseModel):
    """Result of server-side VLM camera proctoring for one frame."""

    compliant: bool
    face_visible: bool
    face_count: int = Field(ge=0)
    identity_match_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    violations: list[CameraViolationRead]
    events_recorded: list[ProctoringEventRead]


class AudioAnalyzeRequest(BaseModel):
    """Client-reported microphone signal summary (no raw audio stored)."""

    session_id: str = Field(min_length=1, max_length=36)
    average_rms: float = Field(ge=0.0, le=1.0)
    microphone_muted: bool = False
    microphone_enabled: bool = True
    client_timestamp: Optional[datetime] = None


class AudioViolationRead(BaseModel):
    event_type: ProctoringEventType
    severity: ProctoringSeverity
    description: str


class AudioAnalyzeResponse(BaseModel):
    compliant: bool
    violations: list[AudioViolationRead]
    events_recorded: list[ProctoringEventRead]


class SessionIntegritySummary(BaseModel):
    """Published contract for session integrity — consumed by FE and reports."""

    session_id: str
    verification_status: VerificationStatus
    high_severity_count: int = Field(ge=0)
    threshold: int = Field(ge=1)
    identity_verified: bool
    events: list[ProctoringEventRead]


class SessionIntegritySnapshot(BaseModel):
    """Lightweight integrity view embedded in session and report contracts."""

    verification_status: VerificationStatus
    high_severity_count: int = Field(ge=0)
    threshold: int = Field(ge=1)
    identity_verified: bool
