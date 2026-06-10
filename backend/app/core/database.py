"""Async database engine, SQLModel base, session factory, and DI helpers.

This module is the foundation every feature's ``models.py`` and ``api.py``
builds on. It exposes a single pooled async engine, an
:func:`~sqlalchemy.ext.asyncio.async_sessionmaker` session factory that yields
SQLModel-aware :class:`AsyncSession` objects, the :class:`TimestampMixin`, the
:func:`get_db` FastAPI dependency, and a :func:`check_db_connection` health
probe.

Feature models are defined with SQLModel and import everything they need from
here::

    from app.core.database import SQLModel, Field, TimestampMixin

    class VoiceSession(SQLModel, TimestampMixin, table=True):
        id: int | None = Field(default=None, primary_key=True)

Everything is SQLModel 2.0 / SQLAlchemy 2.0 style and fully async:
``Field()`` (never ``Column()``), ``select()`` (never ``session.query()``),
``AsyncSession`` only. Schema creation is owned by Alembic migrations — the
application never calls ``create_all()``.
"""

from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from sqlalchemy import DateTime, func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import Field, SQLModel

# VERIFY: SQLModel's async session lives at sqlmodel.ext.asyncio.session on
# sqlmodel==0.0.37. It subclasses SQLAlchemy's AsyncSession and adds .exec(),
# which feature code uses for SQLModel-typed queries.
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings
from app.core.logging import get_logger

_settings = get_settings()
_logger = get_logger(__name__)

#: Process-wide async engine. The pool is sized for the FastAPI layer's
#: concurrency: up to ``pool_size`` persistent connections plus ``max_overflow``
#: burst connections. ``pool_pre_ping`` transparently discards stale connections
#: and ``pool_recycle`` caps connection lifetime so the server never serves a
#: dead socket.
engine = create_async_engine(
    _settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)

#: Session factory bound to :data:`engine`. ``expire_on_commit=False`` keeps ORM
#: instances usable after ``commit()`` (so attributes can be read inside a
#: response handler without triggering a fresh, already-closed query).
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class TimestampMixin:
    """Adds timezone-aware ``created_at`` / ``updated_at`` audit columns.

    Mix this in alongside :class:`~sqlmodel.SQLModel` for any table that should
    track creation and last-modification times::

        class VoiceSession(SQLModel, TimestampMixin, table=True): ...

    Both columns are timezone-aware and populated by the database server clock
    (``server_default`` / ``onupdate``), so timestamps stay consistent
    regardless of which worker writes the row. A Python-side ``default_factory``
    provides a value for instances that are inspected before flush.

    Attributes:
        created_at: Server-set timestamp of row insertion.
        updated_at: Server-set timestamp of insertion, refreshed on every update.
    """

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now()},
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now(), "onupdate": func.now()},
        nullable=False,
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a transactional :class:`AsyncSession` for a single request.

    Intended for use as a FastAPI dependency. The session commits when the
    request handler returns cleanly, rolls back if it raises, and is always
    closed afterwards.

    Yields:
        An :class:`AsyncSession` bound to the request's transaction.

    Raises:
        Exception: Re-raises any exception from the request handler after
            rolling back the transaction.
    """
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_connection() -> bool:
    """Verify the database is reachable by issuing ``SELECT 1``.

    Used by the application's health-check endpoint. Never raises — any
    connectivity or driver error is logged and reported as ``False``.

    Returns:
        ``True`` if the query succeeds, ``False`` otherwise.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        _logger.error("db_connection_failed", error=str(exc))
        return False
    _logger.info("db_connection_established")
    return True


__all__ = [
    "engine",
    "async_session",
    "SQLModel",
    "Field",
    "TimestampMixin",
    "get_db",
    "check_db_connection",
]
