"""Background task workers (Celery). Enable via docker compose --profile worker."""

from app.workers.celery_app import celery_app

__all__ = ["celery_app"]
