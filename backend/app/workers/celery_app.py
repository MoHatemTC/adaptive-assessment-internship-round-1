"""Celery application for async grading/report jobs (Phase 7+).

The worker service is opt-in in docker-compose (``--profile worker``) until
background tasks are registered here.
"""

from __future__ import annotations

from celery import Celery

from app.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "masaar",
    broker=_settings.REDIS_URL,
    backend=_settings.REDIS_URL,
)

celery_app.conf.update(
    task_default_queue="default",
    task_track_started=True,
    worker_prefetch_multiplier=1,
)

__all__ = ["celery_app"]
