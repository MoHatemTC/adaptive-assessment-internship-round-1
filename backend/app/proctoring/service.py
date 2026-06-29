"""Proctoring business logic — events, verification status, and session flagging."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.admin.models import Assessment
from app.core.logging import get_logger
from app.proctoring.audio_monitor import analyze_audio_signal
from app.proctoring.events_catalog import (
    EVENT_DEFAULT_SEVERITIES,
    default_severity,
    is_known_event_type,
    normalize_enabled_checks,
)
from app.proctoring.identity import FaceMatchProvider, IdentityUnavailableError
from app.proctoring.models import ProctoringEvent
from app.proctoring.settings import get_proctoring_settings
from app.proctoring.vlm_face import analyze_camera_frame
from app.sessions.models import AssessmentSession
from app.shared.schemas.proctoring import (
    AudioAnalyzeRequest,
    AudioAnalyzeResponse,
    AudioViolationRead,
    CameraAnalyzeRequest,
    CameraAnalyzeResponse,
    CameraViolationRead,
    IdentityVerifyRequest,
    IdentityVerifyResponse,
    ProctoringEventBatchCreate,
    ProctoringEventBatchResponse,
    ProctoringEventCreate,
    ProctoringEventRead,
    ProctoringEventType,
    ProctoringPolicy,
    ProctoringPolicyResponse,
    ProctoringSeverity,
    SessionIntegritySummary,
    SessionIntegritySnapshot,
    VerificationStatus,
)

_logger = get_logger(__name__)

_TERMINAL_SESSION_STATUSES = frozenset({"completed", "expired"})


def _parse_json_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _serialize_metadata(metadata: dict[str, Any] | None) -> str | None:
    if metadata is None:
        return None
    return json.dumps(metadata)


def _deserialize_metadata(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    parsed = _parse_json_dict(raw)
    return parsed or None


def _event_to_read(event: ProctoringEvent) -> ProctoringEventRead:
    return ProctoringEventRead(
        id=event.id,
        session_id=event.session_id,
        event_type=event.event_type,  # type: ignore[arg-type]
        severity=event.severity,  # type: ignore[arg-type]
        metadata=_deserialize_metadata(event.metadata_json),
        client_timestamp=event.client_timestamp,
        created_at=event.created_at,
    )


def _high_severity_count(events: Sequence[ProctoringEvent]) -> int:
    return sum(1 for event in events if event.severity == "high")


def _has_event_type(events: Sequence[ProctoringEvent], event_type: str) -> bool:
    return any(event.event_type == event_type for event in events)


def compute_verification_status(
    *,
    session_status: str,
    events: Sequence[ProctoringEvent],
    policy: ProctoringPolicy,
) -> VerificationStatus:
    """Derive verification status from session state and recorded events."""
    if _has_event_type(events, "identity_fail"):
        return "identity_failed"

    high_count = _high_severity_count(events)
    if session_status == "flagged" or high_count >= policy.high_severity_threshold:
        return "flagged"

    if _has_event_type(events, "identity_verified"):
        return "verified"

    return "pending"


async def _get_session_or_404(db: AsyncSession, session_id: str) -> AssessmentSession:
    session = await db.get(AssessmentSession, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="assessment session not found",
        )
    return session


async def resolve_policy(db: AsyncSession, session: AssessmentSession) -> ProctoringPolicy:
    """Resolve proctoring policy from assessment admin configuration."""
    assessment = await db.get(Assessment, session.assessment_id)
    threshold: int | None = None
    enabled_checks: list[str] | None = None
    camera_poll_interval_seconds = 1.5
    event_cooldown_seconds = 30
    require_camera = True
    require_microphone = False

    def _apply_cfg(cfg: dict[str, Any]) -> None:
        nonlocal threshold, enabled_checks, camera_poll_interval_seconds
        nonlocal event_cooldown_seconds, require_camera, require_microphone

        raw_threshold = cfg.get("high_severity_threshold")
        if isinstance(raw_threshold, int) and raw_threshold >= 1:
            threshold = raw_threshold

        raw_checks = cfg.get("enabled_checks")
        if isinstance(raw_checks, list):
            enabled_checks = [str(item) for item in raw_checks]

        raw_poll = cfg.get("camera_poll_interval_seconds")
        if isinstance(raw_poll, (int, float)) and 1.0 <= float(raw_poll) <= 2.0:
            camera_poll_interval_seconds = float(raw_poll)

        raw_cooldown = cfg.get("event_cooldown_seconds")
        if isinstance(raw_cooldown, int) and 0 <= raw_cooldown <= 300:
            event_cooldown_seconds = raw_cooldown

        if "require_camera" in cfg:
            require_camera = bool(cfg["require_camera"])
        if "require_microphone" in cfg:
            require_microphone = bool(cfg["require_microphone"])

    if assessment is not None:
        tool_config = _parse_json_dict(assessment.tool_config)
        proctoring_cfg = tool_config.get("proctoring")
        if isinstance(proctoring_cfg, dict):
            _apply_cfg(proctoring_cfg)

        if threshold is None:
            blueprint = _parse_json_dict(assessment.blueprint_json)
            proctoring_blueprint = blueprint.get("proctoring")
            if isinstance(proctoring_blueprint, dict):
                _apply_cfg(proctoring_blueprint)

    if threshold is None:
        threshold = get_proctoring_settings().PROCTORING_HIGH_SEVERITY_THRESHOLD

    return ProctoringPolicy(
        high_severity_threshold=threshold,
        enabled_checks=normalize_enabled_checks(enabled_checks),
        camera_poll_interval_seconds=camera_poll_interval_seconds,
        event_cooldown_seconds=event_cooldown_seconds,
        require_camera=require_camera,
        require_microphone=require_microphone,
    )


async def get_session_policy(
    db: AsyncSession,
    session_id: str,
) -> ProctoringPolicyResponse:
    """Return the resolved policy and severity defaults for a session."""
    session = await _get_session_or_404(db, session_id)
    policy = await resolve_policy(db, session)
    return ProctoringPolicyResponse(
        session_id=session_id,
        default_severities=dict(EVENT_DEFAULT_SEVERITIES),
        **policy.model_dump(),
    )


async def _recent_duplicate_event(
    db: AsyncSession,
    session_id: str,
    event_type: str,
    cooldown_seconds: int,
) -> ProctoringEvent | None:
    if cooldown_seconds <= 0:
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=cooldown_seconds)
    result = await db.exec(
        select(ProctoringEvent)
        .where(ProctoringEvent.session_id == session_id)
        .where(ProctoringEvent.event_type == event_type)
        .where(ProctoringEvent.created_at >= cutoff)
        .order_by(ProctoringEvent.created_at.desc())
        .limit(1)
    )
    return result.first()


async def _persist_proctoring_event(
    db: AsyncSession,
    *,
    session: AssessmentSession,
    policy: ProctoringPolicy,
    event_type: str,
    severity: ProctoringSeverity,
    metadata: dict[str, Any] | None = None,
    client_timestamp: datetime | None = None,
    enforce_cooldown: bool = True,
) -> ProctoringEventRead | None:
    """Insert an event when enabled and outside the cooldown window."""
    if event_type not in policy.enabled_checks:
        return None

    if enforce_cooldown:
        duplicate = await _recent_duplicate_event(
            db,
            session.id,
            event_type,
            policy.event_cooldown_seconds,
        )
        if duplicate is not None:
            return None

    event = ProctoringEvent(
        session_id=session.id,
        event_type=event_type,
        severity=severity,
        metadata_json=_serialize_metadata(metadata),
        client_timestamp=client_timestamp,
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)
    return _event_to_read(event)


async def _persist_lifecycle_event(
    db: AsyncSession,
    *,
    session: AssessmentSession,
    event_type: ProctoringEventType,
    metadata: dict[str, Any] | None = None,
) -> ProctoringEventRead:
    """Record server-owned lifecycle events (always persisted)."""
    if not is_known_event_type(event_type):
        raise ValueError(f"unknown lifecycle event type: {event_type}")

    event = ProctoringEvent(
        session_id=session.id,
        event_type=event_type,
        severity=default_severity(event_type),  # type: ignore[arg-type]
        metadata_json=_serialize_metadata(metadata),
        client_timestamp=None,
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)
    _logger.info(
        "proctoring_lifecycle_event",
        session_id=session.id,
        event_type=event_type,
    )
    return _event_to_read(event)


async def start_proctoring_session(
    db: AsyncSession,
    session_id: str,
    *,
    assessment_type: str | None = None,
) -> ProctoringPolicyResponse:
    """Activate proctoring for a platform session and return the resolved policy."""
    session = await _get_session_or_404(db, session_id)
    policy = await resolve_policy(db, session)

    if session.proctoring_status != "active":
        session.proctoring_status = "active"
        db.add(session)
        await _persist_lifecycle_event(
            db,
            session=session,
            event_type="session_started",
            metadata={"assessment_type": assessment_type} if assessment_type else None,
        )

    return ProctoringPolicyResponse(
        session_id=session_id,
        default_severities=dict(EVENT_DEFAULT_SEVERITIES),
        **policy.model_dump(),
    )


async def stop_proctoring_session(db: AsyncSession, session_id: str) -> None:
    """Deactivate proctoring and record session stop."""
    session = await _get_session_or_404(db, session_id)
    if session.proctoring_status == "stopped":
        return

    session.proctoring_status = "stopped"
    db.add(session)
    await _persist_lifecycle_event(
        db,
        session=session,
        event_type="session_stopped",
    )


async def _prepare_client_event(
    payload: ProctoringEventCreate,
    policy: ProctoringPolicy,
) -> tuple[ProctoringSeverity, dict[str, Any] | None] | None:
    """Validate a client event and return authoritative severity, or None to skip."""
    if not is_known_event_type(payload.event_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown proctoring event type: {payload.event_type}",
        )
    if payload.event_type not in policy.enabled_checks:
        return None

    severity = default_severity(payload.event_type)
    return severity, payload.metadata


async def _load_session_events(
    db: AsyncSession, session_id: str
) -> list[ProctoringEvent]:
    result = await db.exec(
        select(ProctoringEvent)
        .where(ProctoringEvent.session_id == session_id)
        .order_by(ProctoringEvent.created_at.asc())
    )
    return list(result.all())


async def _maybe_flag_session(
    db: AsyncSession,
    session: AssessmentSession,
    policy: ProctoringPolicy,
) -> None:
    if session.status in _TERMINAL_SESSION_STATUSES:
        return

    events = await _load_session_events(db, session.id)
    high_count = _high_severity_count(events)
    if high_count >= policy.high_severity_threshold and session.status != "flagged":
        session.status = "flagged"
        db.add(session)
        await db.flush()
        _logger.info(
            "session_flagged",
            session_id=session.id,
            high_severity_count=high_count,
            threshold=policy.high_severity_threshold,
        )


async def record_event(
    db: AsyncSession,
    payload: ProctoringEventCreate,
) -> ProctoringEventRead:
    """Persist an integrity event and apply threshold flagging when needed."""
    session = await _get_session_or_404(db, payload.session_id)
    if session.status in _TERMINAL_SESSION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session is no longer active",
        )

    policy = await resolve_policy(db, session)
    prepared = await _prepare_client_event(payload, policy)
    if prepared is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"event type {payload.event_type!r} is disabled for this session",
        )

    severity, metadata = prepared
    duplicate = await _recent_duplicate_event(
        db,
        session.id,
        payload.event_type,
        policy.event_cooldown_seconds,
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"event {payload.event_type!r} is within cooldown window",
        )

    event_read = await _persist_proctoring_event(
        db,
        session=session,
        policy=policy,
        event_type=payload.event_type,
        severity=severity,
        metadata=metadata,
        client_timestamp=payload.client_timestamp,
        enforce_cooldown=False,
    )
    assert event_read is not None

    await _maybe_flag_session(db, session, policy)
    return event_read


async def record_events_batch(
    db: AsyncSession,
    payload: ProctoringEventBatchCreate,
) -> ProctoringEventBatchResponse:
    """Persist multiple integrity events, skipping cooldown/disabled entries."""
    session = await _get_session_or_404(db, payload.session_id)
    if session.status in _TERMINAL_SESSION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session is no longer active",
        )

    policy = await resolve_policy(db, session)
    recorded: list[ProctoringEventRead] = []
    skipped: list[dict[str, Any]] = []

    for item in payload.events:
        if item.session_id != payload.session_id:
            skipped.append(
                {
                    "event_type": item.event_type,
                    "reason": "session_id mismatch",
                }
            )
            continue

        try:
            prepared = await _prepare_client_event(item, policy)
        except HTTPException as exc:
            skipped.append(
                {
                    "event_type": item.event_type,
                    "reason": str(exc.detail),
                }
            )
            continue

        if prepared is None:
            skipped.append(
                {
                    "event_type": item.event_type,
                    "reason": "disabled",
                }
            )
            continue

        severity, metadata = prepared
        event_read = await _persist_proctoring_event(
            db,
            session=session,
            policy=policy,
            event_type=item.event_type,
            severity=severity,
            metadata=metadata,
            client_timestamp=item.client_timestamp,
            enforce_cooldown=True,
        )
        if event_read is None:
            skipped.append(
                {
                    "event_type": item.event_type,
                    "reason": "cooldown",
                }
            )
            continue
        recorded.append(event_read)

    if recorded:
        await _maybe_flag_session(db, session, policy)

    return ProctoringEventBatchResponse(recorded=recorded, skipped=skipped)


async def get_session_events(
    db: AsyncSession,
    session_id: str,
) -> list[ProctoringEventRead]:
    """Return all integrity events for a session."""
    await _get_session_or_404(db, session_id)
    events = await _load_session_events(db, session_id)
    return [_event_to_read(event) for event in events]


async def get_session_integrity(
    db: AsyncSession,
    session_id: str,
) -> SessionIntegritySummary:
    """Build the published integrity summary contract."""
    session = await _get_session_or_404(db, session_id)
    policy = await resolve_policy(db, session)
    events = await _load_session_events(db, session_id)
    event_reads = [_event_to_read(event) for event in events]

    verification_status = compute_verification_status(
        session_status=session.status,
        events=events,
        policy=policy,
    )

    return SessionIntegritySummary(
        session_id=session_id,
        verification_status=verification_status,
        high_severity_count=_high_severity_count(events),
        threshold=policy.high_severity_threshold,
        identity_verified=_has_event_type(events, "identity_verified"),
        events=event_reads,
    )


async def get_integrity_snapshot(
    db: AsyncSession,
    session_id: str,
) -> SessionIntegritySnapshot:
    """Return a lightweight integrity snapshot for session/report contracts."""
    summary = await get_session_integrity(db, session_id)
    return SessionIntegritySnapshot(
        verification_status=summary.verification_status,
        high_severity_count=summary.high_severity_count,
        threshold=summary.threshold,
        identity_verified=summary.identity_verified,
    )


async def verify_identity(
    db: AsyncSession,
    payload: IdentityVerifyRequest,
    face_provider: FaceMatchProvider,
) -> IdentityVerifyResponse:
    """Verify learner identity via face match before the assessment begins."""
    session = await _get_session_or_404(db, payload.session_id)

    if session.status in _TERMINAL_SESSION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session is no longer active",
        )

    profile = _parse_json_dict(session.learner_profile_json)
    if not profile.get("consent_given"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="camera consent is required before identity verification",
        )

    existing = await _load_session_events(db, session.id)
    if _has_event_type(existing, "identity_verified"):
        policy = await resolve_policy(db, session)
        return IdentityVerifyResponse(
            verified=True,
            match_score=None,
            verification_status=compute_verification_status(
                session_status=session.status,
                events=existing,
                policy=policy,
            ),
            message="identity already verified for this session",
        )

    try:
        match = await face_provider.compare(
            payload.reference_image_b64,
            payload.live_capture_b64,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except IdentityUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    policy = await resolve_policy(db, session)
    event_type = "identity_verified" if match.matched else "identity_fail"
    severity: ProctoringSeverity = "low" if match.matched else "high"

    event = ProctoringEvent(
        session_id=session.id,
        event_type=event_type,
        severity=severity,
        metadata_json=_serialize_metadata({"match_score": match.score}),
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)

    if not match.matched:
        return IdentityVerifyResponse(
            verified=False,
            match_score=match.score,
            verification_status="identity_failed",
            message="identity verification failed",
        )

    await _maybe_flag_session(db, session, policy)

    refreshed_events = await _load_session_events(db, session.id)
    await db.refresh(session)

    verification_status = compute_verification_status(
        session_status=session.status,
        events=refreshed_events,
        policy=policy,
    )

    return IdentityVerifyResponse(
        verified=True,
        match_score=match.score,
        verification_status=verification_status,
        message="identity verified",
    )


async def analyze_camera(
    db: AsyncSession,
    payload: CameraAnalyzeRequest,
) -> CameraAnalyzeResponse:
    """Analyze a live camera frame with the VLM and record violations."""
    session = await _get_session_or_404(db, payload.session_id)

    if session.status in _TERMINAL_SESSION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session is no longer active",
        )

    profile = _parse_json_dict(session.learner_profile_json)
    if not profile.get("consent_given"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="camera consent is required before camera proctoring",
        )

    settings = get_proctoring_settings()
    if not settings.vlm_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="vision proctoring is not configured (set LITELLM_API_KEY)",
        )

    try:
        analysis, violations = await analyze_camera_frame(
            payload.frame_b64,
            reference_b64=payload.reference_image_b64,
            match_threshold=settings.FACE_MATCH_THRESHOLD,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except IdentityUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    policy = await resolve_policy(db, session)
    recorded: list[ProctoringEventRead] = []

    for violation in violations:
        metadata: dict[str, Any] = {
            "description": violation.description,
            "face_count": analysis.face_count,
            "face_visible": analysis.face_visible,
        }
        if analysis.identity_match_score is not None:
            metadata["identity_match_score"] = analysis.identity_match_score

        event_read = await _persist_proctoring_event(
            db,
            session=session,
            policy=policy,
            event_type=violation.event_type,
            severity=violation.severity,
            metadata=metadata,
            client_timestamp=payload.client_timestamp,
            enforce_cooldown=True,
        )
        if event_read is not None:
            recorded.append(event_read)

    if recorded:
        await _maybe_flag_session(db, session, policy)

    violation_reads = [
        CameraViolationRead(
            event_type=violation.event_type,
            severity=violation.severity,
            description=violation.description,
        )
        for violation in violations
    ]

    return CameraAnalyzeResponse(
        compliant=len(violations) == 0,
        face_visible=analysis.face_visible,
        face_count=analysis.face_count,
        identity_match_score=analysis.identity_match_score,
        violations=violation_reads,
        events_recorded=recorded,
    )


async def analyze_audio(
    db: AsyncSession,
    payload: AudioAnalyzeRequest,
) -> AudioAnalyzeResponse:
    """Evaluate client-reported microphone metrics and record violations."""
    session = await _get_session_or_404(db, payload.session_id)

    if session.status in _TERMINAL_SESSION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session is no longer active",
        )

    profile = _parse_json_dict(session.learner_profile_json)
    if not profile.get("consent_given"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="consent is required before audio proctoring",
        )

    policy = await resolve_policy(db, session)
    violations = analyze_audio_signal(
        average_rms=payload.average_rms,
        microphone_muted=payload.microphone_muted,
        microphone_enabled=payload.microphone_enabled,
    )

    recorded: list[ProctoringEventRead] = []
    for violation in violations:
        event_read = await _persist_proctoring_event(
            db,
            session=session,
            policy=policy,
            event_type=violation.event_type,
            severity=violation.severity,
            metadata={"description": violation.description, "average_rms": payload.average_rms},
            client_timestamp=payload.client_timestamp,
            enforce_cooldown=True,
        )
        if event_read is not None:
            recorded.append(event_read)

    if recorded:
        await _maybe_flag_session(db, session, policy)

    violation_reads = [
        AudioViolationRead(
            event_type=violation.event_type,
            severity=violation.severity,
            description=violation.description,
        )
        for violation in violations
    ]

    return AudioAnalyzeResponse(
        compliant=len(violations) == 0,
        violations=violation_reads,
        events_recorded=recorded,
    )
