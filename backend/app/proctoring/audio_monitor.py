"""Client-reported audio signal checks for proctoring."""

from __future__ import annotations

from dataclasses import dataclass

from app.proctoring.events_catalog import default_severity
from app.shared.schemas.proctoring import ProctoringEventType, ProctoringSeverity

_AUDIO_ABSENT_RMS_THRESHOLD = 0.02


@dataclass(frozen=True)
class AudioViolation:
    event_type: ProctoringEventType
    severity: ProctoringSeverity
    description: str


def analyze_audio_signal(
    *,
    average_rms: float,
    microphone_muted: bool,
    microphone_enabled: bool,
) -> list[AudioViolation]:
    """Derive audio integrity violations from client-reported metrics."""
    violations: list[AudioViolation] = []

    if not microphone_enabled:
        violations.append(
            AudioViolation(
                event_type="microphone_disabled",
                severity=default_severity("microphone_disabled"),
                description="Microphone track is disabled",
            )
        )
    if microphone_muted:
        violations.append(
            AudioViolation(
                event_type="microphone_muted",
                severity=default_severity("microphone_muted"),
                description="Microphone is muted",
            )
        )
    if microphone_enabled and not microphone_muted and average_rms < _AUDIO_ABSENT_RMS_THRESHOLD:
        violations.append(
            AudioViolation(
                event_type="audio_absent",
                severity=default_severity("audio_absent"),
                description="No audible signal detected from microphone",
            )
        )

    return violations
