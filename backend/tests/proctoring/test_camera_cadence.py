"""Tests for WP-4 camera cadence helpers (person_count, absence grace)."""

from __future__ import annotations

import time
from unittest.mock import patch

from app.proctoring.vlm_face import (
    CameraAnalysisResult,
    apply_candidate_absence_grace,
    clear_session_camera_state,
    violations_from_analysis,
    _parse_camera_analysis,
)


def _analysis(**kwargs) -> CameraAnalysisResult:
    defaults = dict(
        face_visible=True,
        person_count=1,
        face_count=1,
        camera_obstructed=False,
        looking_at_screen=True,
        identity_match_score=None,
        identity_matches_reference=None,
    )
    defaults.update(kwargs)
    return CameraAnalysisResult(**defaults)


def test_parse_person_count_prefers_explicit_field():
    parsed = _parse_camera_analysis({"person_count": 2, "face_count": 1})
    assert parsed.person_count == 2
    assert parsed.face_count == 2


def test_violations_multiple_persons_detected():
    violations = violations_from_analysis(
        _analysis(person_count=2, face_count=2),
        has_reference=False,
        match_threshold=0.7,
    )
    assert any(v.event_type == "multiple_persons_detected" for v in violations)


def test_violations_no_immediate_absence_when_empty_frame():
    violations = violations_from_analysis(
        _analysis(face_visible=False, person_count=0, face_count=0),
        has_reference=False,
        match_threshold=0.7,
    )
    assert violations == []


def test_absence_grace_emits_candidate_absent_after_delay():
    session_id = "sess-grace-test"
    clear_session_camera_state(session_id)
    empty = _analysis(face_visible=False, person_count=0, face_count=0)

    with patch("app.proctoring.vlm_face.time.monotonic", return_value=10.0):
        assert apply_candidate_absence_grace(session_id, empty, grace_seconds=2.0) is None

    with patch("app.proctoring.vlm_face.time.monotonic", return_value=12.5):
        violation = apply_candidate_absence_grace(session_id, empty, grace_seconds=2.0)

    assert violation is not None
    assert violation.event_type == "candidate_absent"
    clear_session_camera_state(session_id)


def test_absence_grace_resets_when_person_returns():
    session_id = "sess-reset-test"
    clear_session_camera_state(session_id)
    empty = _analysis(face_visible=False, person_count=0, face_count=0)
    present = _analysis(person_count=1)

    with patch("app.proctoring.vlm_face.time.monotonic", return_value=10.0):
        apply_candidate_absence_grace(session_id, empty, grace_seconds=2.0)

    with patch("app.proctoring.vlm_face.time.monotonic", return_value=11.0):
        apply_candidate_absence_grace(session_id, present, grace_seconds=2.0)

    with patch("app.proctoring.vlm_face.time.monotonic", return_value=12.0):
        assert apply_candidate_absence_grace(session_id, empty, grace_seconds=2.0) is None

    with patch("app.proctoring.vlm_face.time.monotonic", return_value=13.5):
        assert apply_candidate_absence_grace(session_id, empty, grace_seconds=2.0) is None

    clear_session_camera_state(session_id)
