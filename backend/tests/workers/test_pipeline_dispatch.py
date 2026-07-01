"""Tests for Celery pipeline dispatch helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.workers import pipeline_dispatch


def test_dispatch_pipeline_task_uses_background_when_celery_disabled():
    coro = MagicMock()
    with (
        patch.object(pipeline_dispatch, "celery_pipelines_enabled", return_value=False),
        patch.object(pipeline_dispatch, "schedule_background") as schedule_mock,
    ):
        pipeline_dispatch.dispatch_pipeline_task(
            "pipelines.mcq.start",
            kwargs={"session_id": "sess-1"},
            background_coro=coro,
            background_key="mcq:start:sess-1",
        )

    schedule_mock.assert_called_once_with(
        coro,
        key="mcq:start:sess-1",
        force=False,
    )


def test_dispatch_pipeline_task_uses_celery_when_enabled():
    coro = MagicMock()
    with (
        patch.object(pipeline_dispatch, "celery_pipelines_enabled", return_value=True),
        patch.object(pipeline_dispatch.celery_app, "send_task") as send_mock,
        patch.object(pipeline_dispatch, "schedule_background") as schedule_mock,
    ):
        pipeline_dispatch.dispatch_pipeline_task(
            "pipelines.mcq.start",
            kwargs={"session_id": "sess-1"},
            background_coro=coro,
            background_key="mcq:start:sess-1",
        )

    send_mock.assert_called_once_with(
        "pipelines.mcq.start",
        kwargs={"session_id": "sess-1"},
    )
    schedule_mock.assert_not_called()
