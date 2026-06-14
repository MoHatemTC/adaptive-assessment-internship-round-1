"""Timer helpers for timed code assessment sessions."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def remaining_seconds(expires_at: datetime) -> int:
    delta = (_aware(expires_at) - utcnow()).total_seconds()
    return max(0, int(delta))


def assert_active(expires_at: datetime, *, label: str) -> int:
    remaining = remaining_seconds(expires_at)
    if remaining <= 0:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"{label} has expired",
        )
    return remaining
