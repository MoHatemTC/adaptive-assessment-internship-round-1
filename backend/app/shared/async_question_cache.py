"""Shared helpers for async question-generation session caches."""

from __future__ import annotations

import time

DEFAULT_GENERATION_STALE_SECONDS = 90


def generation_should_schedule(
    cache: dict,
    *,
    stale_seconds: float = DEFAULT_GENERATION_STALE_SECONDS,
) -> bool:
    """Return True when a background generator should be (re)started."""
    status = str(cache.get("status") or "idle")
    if status in {"idle", "failed"}:
        return True
    if status == "ready":
        return False
    if status == "generating":
        started = cache.get("started_at")
        if started is None:
            return True
        try:
            elapsed = time.time() - float(started)
        except (TypeError, ValueError):
            return True
        return elapsed >= stale_seconds
    return True


def generation_is_stale(
    cache: dict,
    *,
    stale_seconds: float = DEFAULT_GENERATION_STALE_SECONDS,
) -> bool:
    """Return True when ``generating`` has exceeded the stale threshold."""
    if str(cache.get("status") or "") != "generating":
        return False
    started = cache.get("started_at")
    if started is None:
        return True
    try:
        return (time.time() - float(started)) >= stale_seconds
    except (TypeError, ValueError):
        return True


__all__ = [
    "DEFAULT_GENERATION_STALE_SECONDS",
    "generation_is_stale",
    "generation_should_schedule",
]
