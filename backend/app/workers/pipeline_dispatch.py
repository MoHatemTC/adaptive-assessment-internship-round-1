"""Dispatch background pipelines to Celery or in-process asyncio tasks."""

from __future__ import annotations

from collections.abc import Coroutine
from typing import Any

from app.config import get_settings
from app.core.background_tasks import schedule_background
from app.workers.celery_app import celery_app

_CELERY_TRUTHY = frozenset({"1", "true", "yes", "on"})


def celery_pipelines_enabled() -> bool:
    """Return True when tool pipelines should run on Celery workers."""
    return get_settings().CELERY_PIPELINES


def dispatch_pipeline_task(
    task_name: str,
    *,
    kwargs: dict[str, Any],
    background_coro: Coroutine[Any, Any, None],
    background_key: str | None = None,
    force: bool = False,
) -> None:
    """Enqueue a Celery task or fall back to ``schedule_background``."""
    if celery_pipelines_enabled():
        celery_app.send_task(task_name, kwargs=kwargs)
        return
    schedule_background(background_coro, key=background_key, force=force)


__all__ = ["celery_pipelines_enabled", "dispatch_pipeline_task"]
