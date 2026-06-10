"""LangGraph Postgres checkpointer for persistent, resumable agent state.

Every examiner-agent session persists its graph state to Postgres through
:class:`~langgraph.checkpoint.postgres.aio.AsyncPostgresSaver`. That lets a
session survive a process crash or redeploy and resume exactly where it left off
— mid-assessment, mid-interview — instead of restarting. Using Postgres (the
same database that holds application data) keeps checkpoint state durable and
backed up alongside everything else.

Driver note: the SQLAlchemy engine in :mod:`app.core.database` talks to Postgres
via **asyncpg** (``postgresql+asyncpg://``), but ``AsyncPostgresSaver`` uses
**psycopg3** and needs a plain ``postgresql://`` URL. :func:`_build_psycopg_url`
derives that psycopg URL from ``DATABASE_URL`` by stripping the ``+asyncpg``
dialect suffix.

Local-dev fallback: if Postgres is unreachable in the development environment,
:func:`get_checkpointer` yields an in-memory
:class:`~langgraph.checkpoint.memory.MemorySaver` so the app still runs. In
production an unreachable checkpointer is a hard failure and raises.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit, urlunsplit

import psycopg

# VERIFY: on langgraph-checkpoint-postgres==3.0.3 the async saver is at
# langgraph.checkpoint.postgres.aio and the base class at
# langgraph.checkpoint.base. MemorySaver ships with langgraph itself.
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import get_settings
from app.core.logging import get_logger

_logger = get_logger(__name__)

#: SQLAlchemy async dialect prefix used by the application engine.
_ASYNCPG_PREFIX = "postgresql+asyncpg://"

#: Plain psycopg-compatible prefix expected by AsyncPostgresSaver.
_PSYCOPG_PREFIX = "postgresql://"


def _build_psycopg_url(db_url: str) -> str:
    """Convert a SQLAlchemy asyncpg URL into a plain psycopg URL.

    ``AsyncPostgresSaver`` connects with psycopg3, which does not understand the
    ``+asyncpg`` SQLAlchemy dialect suffix. This swaps the scheme while leaving
    credentials, host, port, and database path untouched.

    Args:
        db_url: The application ``DATABASE_URL`` (``postgresql+asyncpg://...``).

    Returns:
        The equivalent ``postgresql://...`` URL for psycopg.
    """
    return db_url.replace(_ASYNCPG_PREFIX, _PSYCOPG_PREFIX, 1)


def _mask_db_url(url: str) -> str:
    """Return ``url`` with any embedded password replaced by ``***``.

    Used so connection-error messages can name the failing database without
    exposing credentials.

    Args:
        url: A database connection URL, possibly containing ``user:password@``.

    Returns:
        The URL with its password component masked. If the URL cannot be parsed,
        a fully redacted placeholder is returned rather than risking a leak.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return "postgresql://***"
    if parts.password is None:
        return url
    user = parts.username or ""
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port is not None else ""
    netloc = f"{user}:***@{host}{port}" if user else f":***@{host}{port}"
    return urlunsplit(
        (parts.scheme, netloc, parts.path, parts.query, parts.fragment)
    )


@asynccontextmanager
async def get_checkpointer() -> AsyncGenerator[BaseCheckpointSaver, None]:
    """Open a Postgres-backed LangGraph checkpointer for the duration of a scope.

    Use directly as ``async with get_checkpointer() as checkpointer: ...`` when
    compiling or invoking a graph, or via the ``get_checkpointer_dep`` FastAPI
    dependency. The underlying psycopg connection is always closed on exit.

    In the development environment, if Postgres cannot be reached, an in-memory
    :class:`MemorySaver` is yielded as a fallback so local work is unblocked. In
    every other environment an unreachable database raises.

    Yields:
        A ready-to-use checkpointer (``AsyncPostgresSaver``, or ``MemorySaver``
        as a development fallback).

    Raises:
        RuntimeError: If Postgres is unreachable outside development. The message
            includes the database URL with its password masked.
    """
    settings = get_settings()
    psycopg_url = _build_psycopg_url(settings.DATABASE_URL)
    try:
        async with AsyncPostgresSaver.from_conn_string(psycopg_url) as saver:
            yield saver
    except (psycopg.Error, OSError) as exc:
        masked = _mask_db_url(psycopg_url)
        _logger.error("checkpointer_connection_failed", database=masked)
        if settings.is_development:
            _logger.warning("checkpointer_fallback_memory")
            yield MemorySaver()
            return
        raise RuntimeError(
            f"Could not connect to the Postgres checkpointer at {masked}."
        ) from exc


async def setup_checkpointer() -> None:
    """Provision the LangGraph checkpoint tables in Postgres.

    Creates the tables/indices ``AsyncPostgresSaver`` relies on. Safe to call on
    every startup; the underlying setup is idempotent. Invoke this once during
    the application lifespan, before any agent session runs.

    In development, a connection failure is logged and swallowed (the in-memory
    fallback needs no setup). In other environments it raises.

    Raises:
        RuntimeError: If Postgres is unreachable outside development. The message
            includes the database URL with its password masked.
    """
    settings = get_settings()
    psycopg_url = _build_psycopg_url(settings.DATABASE_URL)
    _logger.info("checkpointer_setup_started")
    try:
        async with AsyncPostgresSaver.from_conn_string(psycopg_url) as saver:
            await saver.setup()
    except (psycopg.Error, OSError) as exc:
        masked = _mask_db_url(psycopg_url)
        _logger.error("checkpointer_connection_failed", database=masked)
        if settings.is_development:
            _logger.warning("checkpointer_fallback_memory")
            return
        raise RuntimeError(
            f"Could not initialise the Postgres checkpointer schema at {masked}."
        ) from exc
    _logger.info("checkpointer_setup_complete")


__all__ = ["get_checkpointer", "setup_checkpointer"]
