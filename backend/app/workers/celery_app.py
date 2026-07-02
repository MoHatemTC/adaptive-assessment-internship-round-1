"""Celery application for async grading/report jobs (Phase 7+).

The worker service is opt-in in docker-compose (``--profile worker``) until
background tasks are registered here.
"""

from __future__ import annotations

from celery import Celery

from app.config import get_settings

_settings = get_settings()
_TASK_TIME_LIMIT_SECONDS = 300
_TASK_SOFT_TIME_LIMIT_SECONDS = 270
_TASK_RETRY_OPTS: dict[str, object] = {
    "autoretry_for": (Exception,),
    "retry_backoff": True,
    "retry_backoff_max": 60,
    "retry_jitter": True,
    "max_retries": 3,
}

celery_app = Celery(
    "masaar",
    broker=_settings.REDIS_URL,
    backend=_settings.REDIS_URL,
)

celery_app.conf.update(
    task_default_queue="default",
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_time_limit=_TASK_TIME_LIMIT_SECONDS,
    task_soft_time_limit=_TASK_SOFT_TIME_LIMIT_SECONDS,
    task_annotations={"*": _TASK_RETRY_OPTS},
    include=[
        "app.workers.report_tasks",
        "app.workers.email_tasks",
        "app.workers.pipeline_tasks",
    ],
)

__all__ = ["celery_app"]
