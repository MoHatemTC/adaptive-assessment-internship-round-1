"""Fire-and-forget asyncio tasks with strong references (avoids GC drops)."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

_tasks: set[asyncio.Task[Any]] = set()
_running_keys: set[str] = set()


def schedule_background(
    coro: Coroutine[Any, Any, None],
    *,
    key: str | None = None,
    force: bool = False,
) -> None:
    """Schedule a coroutine; optional ``key`` deduplicates concurrent runs."""
    if key and not force and key in _running_keys:
        return

    async def _run() -> None:
        if key:
            _running_keys.add(key)
        try:
            await coro
        finally:
            if key:
                _running_keys.discard(key)

    task = asyncio.create_task(_run())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


__all__ = ["schedule_background"]
