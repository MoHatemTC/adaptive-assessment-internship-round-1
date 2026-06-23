"""Tests for proctoring event catalog and audio monitor."""

from app.proctoring.audio_monitor import analyze_audio_signal
from app.proctoring.events_catalog import (
    default_severity,
    normalize_enabled_checks,
)


def test_default_severity_tab_switch():
    assert default_severity("tab_switch") == "medium"


def test_default_severity_paste_is_high():
    assert default_severity("paste") == "high"


def test_normalize_enabled_checks_filters_unknown():
    enabled = normalize_enabled_checks(["tab_switch", "not_real", "paste"])
    assert enabled == ["tab_switch", "paste"]


def test_analyze_audio_signal_detects_muted_mic():
    violations = analyze_audio_signal(
        average_rms=0.5,
        microphone_muted=True,
        microphone_enabled=True,
    )
    assert any(v.event_type == "microphone_muted" for v in violations)


def test_analyze_audio_signal_detects_silence():
    violations = analyze_audio_signal(
        average_rms=0.0,
        microphone_muted=False,
        microphone_enabled=True,
    )
    assert any(v.event_type == "audio_absent" for v in violations)


def test_analyze_audio_signal_detects_disabled_mic():
    violations = analyze_audio_signal(
        average_rms=0.0,
        microphone_muted=False,
        microphone_enabled=False,
    )
    assert any(v.event_type == "microphone_disabled" for v in violations)
