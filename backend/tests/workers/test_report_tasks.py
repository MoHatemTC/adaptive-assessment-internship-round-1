"""Tests for split judge / report Celery tasks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.workers import report_tasks


def test_session_id_from_pipeline_state_accepts_string():
    assert report_tasks._session_id_from_pipeline_state("abc-123") == "abc-123"


def test_session_id_from_pipeline_state_reads_dict():
    assert report_tasks._session_id_from_pipeline_state(
        {"session_id": "abc-123", "status": "confirmed"}
    ) == "abc-123"


def test_build_session_radar_passes_through_pending_review():
    payload = {
        "session_id": "sess-1",
        "status": "pending_admin_review",
        "review_reason": "inconsistent",
    }
    result = report_tasks.build_session_radar_report(payload)
    assert result == payload


@patch("app.workers.report_tasks._run_async")
def test_run_session_judge_task_persists_confirmed(mock_run_async):
    mock_run_async.return_value = {"session_id": "sess-1", "status": "confirmed"}
    payload = report_tasks.run_session_judge_task("sess-1")
    assert payload["status"] == "confirmed"
    mock_run_async.assert_called_once()
