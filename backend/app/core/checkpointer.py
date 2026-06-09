"""LangGraph Redis checkpointer for persistent, resumable agent state.

Every examiner-agent session persists its graph state to Redis through the
:class:`~langgraph.checkpoint.redis.aio.AsyncRedisSaver` exposed here. That
lets a session survive a process crash or redeploy and resume exactly where it
left off — mid-assessment, mid-interview — instead of restarting.

The module offers two entry points:

* :func:`get_checkpointer` — an async context manager that opens a Redis-backed
  saver, yields it, and closes the connection on exit. It is also the building
  block for the FastAPI dependency ``get_checkpointer_dep`` in
  :mod:`app.core.deps`.
* :func:`setup_checkpointer` — a one-shot startup routine that provisions the
  Redis key schema/indices the saver relies on. Call it from the application
  lifespan in ``main.py``.

Connection failures are surfaced as a descriptive :class:`RuntimeError` with the
Redis credentials masked, so an operator sees *which* Redis failed without the
password leaking into logs.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit, urlunsplit

from redis.exceptions import RedisError

# VERIFY: import path for LangGraph 1.2.4's redis checkpointer sub-package
# (langgraph-checkpoint-redis). If `from_conn_string` is unavailable on the
# installed version, fall back to
# `AsyncRedisSaver(redis_client=redis.asyncio.from_url(redis_url))`.
from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from app.config import get_settings


def _mask_redis_url(url: str) -> str:
    """Return ``url`` with any embedded password replaced by ``***``.

    Used so connection-error messages can name the failing Redis instance
    without exposing credentials.

    Args:
        url: A Redis connection URL, possibly containing ``user:password@``.

    Returns:
        The URL with its password component masked. If the URL cannot be
        parsed, a fully redacted placeholder is returned rather than risking a
        leak.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return "redis://***"
    if parts.password is None:
        return url
    user = parts.username or ""
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port is not None else ""
    netloc = f"{user}:***@{host}{port}" if user else f":***@{host}{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


@asynccontextmanager
async def get_checkpointer() -> AsyncGenerator[AsyncRedisSaver, None]:
    """Open a Redis-backed LangGraph checkpointer for the duration of a scope.

    Use directly as ``async with get_checkpointer() as checkpointer: ...`` when
    compiling or invoking a graph, or via the ``get_checkpointer_dep`` FastAPI
    dependency. The underlying Redis connection is always closed on exit.

    Yields:
        A ready-to-use :class:`AsyncRedisSaver` bound to the configured Redis.

    Raises:
        RuntimeError: If the Redis instance cannot be reached. The message
            includes the Redis URL with its password masked.
    """
    redis_url = get_settings().REDIS_URL
    try:
        async with AsyncRedisSaver.from_conn_string(redis_url) as checkpointer:
            yield checkpointer
    except (RedisError, ConnectionError, OSError) as exc:
        raise RuntimeError(
            f"Could not connect to the Redis checkpointer at "
            f"{_mask_redis_url(redis_url)}: {exc}"
        ) from exc


async def setup_checkpointer() -> None:
    """Provision the Redis key schema required by the checkpointer.

    Creates the indices/keys the :class:`AsyncRedisSaver` depends on. Safe to
    call on every startup; the underlying setup is idempotent. Invoke this once
    during the application lifespan, before any agent session runs.

    Raises:
        RuntimeError: If the Redis instance cannot be reached. The message
            includes the Redis URL with its password masked.
    """
    redis_url = get_settings().REDIS_URL
    try:
        async with AsyncRedisSaver.from_conn_string(redis_url) as checkpointer:
            await checkpointer.asetup()  # VERIFY: schema-setup method name
    except (RedisError, ConnectionError, OSError) as exc:
        raise RuntimeError(
            f"Could not initialise the Redis checkpointer schema at "
            f"{_mask_redis_url(redis_url)}: {exc}"
        ) from exc


__all__ = ["get_checkpointer", "setup_checkpointer"]
