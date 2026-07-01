"""Run async coroutines from synchronous Celery task bodies."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Execute a coroutine in a fresh event loop (Celery worker safe)."""
    return asyncio.run(coro)


__all__ = ["run_async"]
