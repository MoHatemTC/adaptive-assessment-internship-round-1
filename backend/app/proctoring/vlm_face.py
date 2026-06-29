"""Vision-language model (Kimi VLM) for camera proctoring."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger
from app.core.vision import VisionGradingUnavailable, acompletion_vision_json
from app.proctoring.identity import (
    FaceMatchResult,
    IdentityUnavailableError,
    _decode_image,
)
from app.proctoring.settings import ProctoringSettings, get_proctoring_settings
from app.shared.schemas.proctoring import ProctoringEventType, ProctoringSeverity

_logger = get_logger(__name__)

MAX_CAMERA_IMAGE_BYTES = 2 * 1024 * 1024

_IDENTITY_COMPARE_PROMPT = """You are a silent identity verifier for online proctoring.
Image 1 is the enrolled reference photo. Image 2 is a live webcam capture.

Decide whether the same person appears in both images. Ignore lighting, angle, and
minor appearance changes; focus on facial identity.

Respond ONLY with a single JSON object — no markdown, no explanation:
{"match_score": <float 0.0-1.0>, "matched": <bool>}"""

_CAMERA_ANALYZE_PROMPT = """You are a silent camera proctor for an online assessment.
Analyze the live webcam frame for integrity violations.

Check:
- Is a human face clearly visible?
- How many distinct people (faces or partial bodies) are visible? Use person_count.
- Is the camera lens covered, black, or unusable?
- Is the person looking toward the screen (not turned far away)?
If a reference photo is included as a second image, estimate whether the live
face matches that enrolled identity.

Respond ONLY with a single JSON object — no markdown, no explanation:
{
  "face_visible": <bool>,
  "person_count": <int>,
  "face_count": <int, same as person_count>,
  "camera_obstructed": <bool>,
  "looking_at_screen": <bool>,
  "identity_match_score": <float 0.0-1.0 or null if no reference>,
  "identity_matches_reference": <bool or null if no reference>
}"""


@dataclass(frozen=True)
class CameraAnalysisResult:
    """Structured output from a live camera frame analysis."""

    face_visible: bool
    person_count: int
    face_count: int
    camera_obstructed: bool
    looking_at_screen: bool
    identity_match_score: float | None
    identity_matches_reference: bool | None


@dataclass(frozen=True)
class CameraViolation:
    """A proctoring violation detected in a camera frame."""

    event_type: ProctoringEventType
    severity: ProctoringSeverity
    description: str


def _data_uri(b64_value: str, mime: str = "image/jpeg") -> str:
    payload = b64_value.strip()
    if payload.startswith("data:"):
        return payload
    return f"data:{mime};base64,{payload}"


def validate_camera_image(b64_value: str) -> bytes:
    """Decode and size-check a camera image payload."""
    raw = _decode_image(b64_value)
    if len(raw) > MAX_CAMERA_IMAGE_BYTES:
        raise ValueError(
            f"Camera image too large: {len(raw)} bytes (max {MAX_CAMERA_IMAGE_BYTES})"
        )
    return raw


def _build_identity_messages(reference_b64: str, live_b64: str) -> list[dict[str, Any]]:
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": _data_uri(reference_b64)},
                },
                {
                    "type": "image_url",
                    "image_url": {"url": _data_uri(live_b64)},
                },
                {"type": "text", "text": _IDENTITY_COMPARE_PROMPT},
            ],
        }
    ]


def _build_camera_messages(
    frame_b64: str,
    reference_b64: str | None = None,
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {
            "type": "image_url",
            "image_url": {"url": _data_uri(frame_b64)},
        },
    ]
    if reference_b64:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": _data_uri(reference_b64)},
            }
        )
    content.append({"type": "text", "text": _CAMERA_ANALYZE_PROMPT})
    return [{"role": "user", "content": content}]


def _clamp_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))


def violations_from_analysis(
    analysis: CameraAnalysisResult,
    *,
    has_reference: bool,
    match_threshold: float,
) -> list[CameraViolation]:
    """Map VLM analysis fields to proctoring violation events."""
    found: list[CameraViolation] = []

    if analysis.camera_obstructed:
        found.append(
            CameraViolation(
                event_type="camera_obstructed",
                severity="high",
                description="Camera appears covered or unusable",
            )
        )
    if not analysis.face_visible and analysis.person_count > 0:
        found.append(
            CameraViolation(
                event_type="face_absent",
                severity="high",
                description="Face not clearly visible despite person in frame",
            )
        )
    if analysis.person_count > 1:
        found.append(
            CameraViolation(
                event_type="multiple_persons_detected",
                severity="high",
                description=f"{analysis.person_count} people detected in frame",
            )
        )
    if analysis.face_visible and not analysis.looking_at_screen:
        found.append(
            CameraViolation(
                event_type="looking_away",
                severity="medium",
                description="Learner not facing the screen",
            )
        )
    if has_reference and analysis.identity_matches_reference is False:
        found.append(
            CameraViolation(
                event_type="identity_mismatch",
                severity="high",
                description="Live face does not match enrolled reference",
            )
        )
    elif (
        has_reference
        and analysis.identity_match_score is not None
        and analysis.identity_match_score < match_threshold
    ):
        found.append(
            CameraViolation(
                event_type="identity_mismatch",
                severity="high",
                description="Identity match score below threshold",
            )
        )

    return found


def _parse_camera_analysis(payload: dict[str, Any]) -> CameraAnalysisResult:
    identity_score = payload.get("identity_match_score")
    parsed_score = None if identity_score is None else _clamp_score(identity_score)
    identity_match = payload.get("identity_matches_reference")
    if identity_match is not None:
        identity_match = bool(identity_match)

    raw_person = payload.get("person_count", payload.get("face_count", 0))
    person_count = max(0, int(raw_person))

    return CameraAnalysisResult(
        face_visible=bool(payload.get("face_visible", False)),
        person_count=person_count,
        face_count=person_count,
        camera_obstructed=bool(payload.get("camera_obstructed", False)),
        looking_at_screen=bool(payload.get("looking_at_screen", True)),
        identity_match_score=parsed_score,
        identity_matches_reference=identity_match,
    )


async def compare_faces_vlm(
    reference_b64: str,
    live_b64: str,
    *,
    threshold: float,
) -> FaceMatchResult:
    """Compare reference and live images via the configured VLM."""
    validate_camera_image(reference_b64)
    validate_camera_image(live_b64)
    messages = _build_identity_messages(reference_b64, live_b64)

    max_tokens = get_proctoring_settings().PROCTORING_VLM_MAX_TOKENS
    try:
        payload = await acompletion_vision_json(messages, max_tokens=max_tokens)
    except VisionGradingUnavailable as exc:
        raise IdentityUnavailableError(str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise IdentityUnavailableError(
            "vision model returned unparseable identity output"
        ) from exc

    score = _clamp_score(payload.get("match_score", 0.0))
    matched = payload.get("matched")
    if matched is None:
        matched = score >= threshold
    else:
        matched = bool(matched)

    _logger.info("vlm_identity_compare", match_score=score, matched=matched)
    return FaceMatchResult(score=score, matched=matched)


async def analyze_camera_frame(
    frame_b64: str,
    *,
    reference_b64: str | None = None,
    match_threshold: float,
) -> tuple[CameraAnalysisResult, list[CameraViolation]]:
    """Analyze a live webcam frame and derive proctoring violations."""
    validate_camera_image(frame_b64)
    if reference_b64:
        validate_camera_image(reference_b64)

    messages = _build_camera_messages(frame_b64, reference_b64)
    max_tokens = get_proctoring_settings().PROCTORING_VLM_MAX_TOKENS
    try:
        payload = await acompletion_vision_json(messages, max_tokens=max_tokens)
    except VisionGradingUnavailable as exc:
        raise IdentityUnavailableError(str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise IdentityUnavailableError(
            "vision model returned unparseable camera output"
        ) from exc

    analysis = _parse_camera_analysis(payload)
    violations = violations_from_analysis(
        analysis,
        has_reference=reference_b64 is not None,
        match_threshold=match_threshold,
    )
    return analysis, violations


# Tracks when a session first showed zero people (grace before candidate_absent).
# NOTE: this is a single-process in-memory dict. With multiple uvicorn workers
# (--workers N) each worker holds its own copy, so the grace timer can reset
# between requests. Acceptable for single-worker deployments; if you scale to
# multiple workers, move this state to Redis or a DB-backed counter.
_absence_started: dict[str, float] = {}


def clear_session_camera_state(session_id: str) -> None:
    """Reset per-session absence grace when proctoring stops."""
    _absence_started.pop(session_id, None)


def apply_candidate_absence_grace(
    session_id: str,
    analysis: CameraAnalysisResult,
    *,
    grace_seconds: float,
) -> CameraViolation | None:
    """Emit candidate_absent only after person_count stays 0 past grace_seconds."""
    if analysis.camera_obstructed or analysis.person_count > 0:
        _absence_started.pop(session_id, None)
        return None

    now = time.monotonic()
    started = _absence_started.get(session_id)
    if started is None:
        _absence_started[session_id] = now
        return None
    if now - started < grace_seconds:
        return None

    return CameraViolation(
        event_type="candidate_absent",
        severity="high",
        description="No person visible in camera frame",
    )


class VLMFaceMatchProvider:
    """Face comparison and camera checks via LiteLLM vision (Kimi VLM)."""

    def __init__(self, settings: ProctoringSettings | None = None) -> None:
        self._settings = settings or get_proctoring_settings()

    async def compare(self, reference_b64: str, live_b64: str) -> FaceMatchResult:
        return await compare_faces_vlm(
            reference_b64,
            live_b64,
            threshold=self._settings.FACE_MATCH_THRESHOLD,
        )
