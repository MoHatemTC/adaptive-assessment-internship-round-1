"""Canonical proctoring event types, default severities, and validation."""

from __future__ import annotations

from typing import Final

from app.shared.schemas.proctoring import ProctoringEventType, ProctoringSeverity

# Browser / input integrity
_BROWSER_EVENTS: dict[ProctoringEventType, ProctoringSeverity] = {
    "tab_switch": "medium",
    "window_blur": "medium",
    "fullscreen_exit": "medium",
    "devtools_open": "high",
    "context_menu": "low",
    "print_attempt": "medium",
    "copy": "medium",
    "paste": "high",
    "copy_paste": "high",
    "screenshot": "high",
    "ai_usage": "high",
    "idle_timeout": "low",
}

# Camera / identity (server or VLM may emit these too)
_CAMERA_EVENTS: dict[ProctoringEventType, ProctoringSeverity] = {
    "identity_verified": "low",
    "identity_fail": "high",
    "identity_mismatch": "high",
    "face_absent": "high",
    "multiple_faces": "high",
    "camera_obstructed": "high",
    "camera_disabled": "high",
    "looking_away": "medium",
}

# Microphone / audio
_AUDIO_EVENTS: dict[ProctoringEventType, ProctoringSeverity] = {
    "microphone_muted": "medium",
    "microphone_disabled": "high",
    "audio_absent": "high",
}

_LIFECYCLE_EVENTS: dict[ProctoringEventType, ProctoringSeverity] = {
    "session_started": "low",
    "session_stopped": "low",
}

EVENT_DEFAULT_SEVERITIES: Final[dict[ProctoringEventType, ProctoringSeverity]] = {
    **_BROWSER_EVENTS,
    **_CAMERA_EVENTS,
    **_AUDIO_EVENTS,
    **_LIFECYCLE_EVENTS,
}

DEFAULT_ENABLED_CHECKS: Final[list[ProctoringEventType]] = list(
    EVENT_DEFAULT_SEVERITIES.keys()
)

# Checks typically monitored only in the browser (not server/VLM pipelines).
CLIENT_MONITOR_CHECKS: Final[frozenset[ProctoringEventType]] = frozenset(
    {
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
        "microphone_muted",
        "microphone_disabled",
        "audio_absent",
        "camera_disabled",
    }
)


def default_severity(event_type: ProctoringEventType) -> ProctoringSeverity:
    """Return the server-authoritative default severity for an event type."""
    return EVENT_DEFAULT_SEVERITIES[event_type]


def is_known_event_type(event_type: str) -> bool:
    return event_type in EVENT_DEFAULT_SEVERITIES


def normalize_enabled_checks(
    raw: list[str] | None,
) -> list[ProctoringEventType]:
    """Filter unknown check names and fall back to the full catalog."""
    if not raw:
        return list(DEFAULT_ENABLED_CHECKS)
    enabled: list[ProctoringEventType] = []
    for name in raw:
        if name in EVENT_DEFAULT_SEVERITIES and name not in enabled:
            enabled.append(name)  # type: ignore[arg-type]
    return enabled or list(DEFAULT_ENABLED_CHECKS)
