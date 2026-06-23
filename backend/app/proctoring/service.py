"""Proctoring business logic — events, verification status, and session flagging."""

from __future__ import annotations

import json
from typing import Any, Sequence

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.admin.models import Assessment
from app.core.logging import get_logger
from app.proctoring.identity import FaceMatchProvider, IdentityUnavailableError
from app.proctoring.models import ProctoringEvent
from app.proctoring.settings import get_proctoring_settings
from app.sessions.models import AssessmentSession
from app.shared.schemas.proctoring import (
    IdentityVerifyRequest,
    IdentityVerifyResponse,
    ProctoringEventCreate,
    ProctoringEventRead,
    ProctoringPolicy,
    ProctoringSeverity,
    SessionIntegritySummary,
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

    if assessment is not None:
        tool_config = _parse_json_dict(assessment.tool_config)
        proctoring_cfg = tool_config.get("proctoring")
        if isinstance(proctoring_cfg, dict):
            raw = proctoring_cfg.get("high_severity_threshold")
            if isinstance(raw, int) and raw >= 1:
                threshold = raw

        if threshold is None:
            blueprint = _parse_json_dict(assessment.blueprint_json)
            proctoring_blueprint = blueprint.get("proctoring")
            if isinstance(proctoring_blueprint, dict):
                raw = proctoring_blueprint.get("high_severity_threshold")
                if isinstance(raw, int) and raw >= 1:
                    threshold = raw

    if threshold is None:
        threshold = get_proctoring_settings().PROCTORING_HIGH_SEVERITY_THRESHOLD

    return ProctoringPolicy(high_severity_threshold=threshold)


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
    policy = await resolve_policy(db, session)

    event = ProctoringEvent(
        session_id=payload.session_id,
        event_type=payload.event_type,
        severity=payload.severity,
        metadata_json=_serialize_metadata(payload.metadata),
        client_timestamp=payload.client_timestamp,
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)

    await _maybe_flag_session(db, session, policy)

    return _event_to_read(event)


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
