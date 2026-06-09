"""Async database engine, session factory, declarative base, and DI helpers.

This module is the foundation every feature's ``models.py`` and ``api.py``
builds on. It exposes a single pooled :class:`~sqlalchemy.ext.asyncio.AsyncEngine`,
an :func:`~sqlalchemy.ext.asyncio.async_sessionmaker` session factory, the
declarative :class:`Base`, a reusable :class:`TimestampMixin`, the
:func:`get_db` FastAPI dependency, and a :func:`check_db_connection` health
probe.

Everything here is SQLAlchemy 2.0 style and fully async: ``Mapped[T]`` /
``mapped_column()`` for models, ``AsyncSession`` for all I/O. The legacy
``Column()`` / ``Session.query()`` / synchronous ``Session`` APIs are never used,
and schema creation is owned by Alembic migrations — not the application.
"""

from collections.abc import AsyncGenerator
from datetime import datetime

from sqlalchemy import DateTime, func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import get_settings

_settings = get_settings()

#: Process-wide async engine. The connection pool is sized for the FastAPI
#: layer's concurrency: up to ``pool_size`` persistent connections plus
#: ``max_overflow`` burst connections. ``pool_pre_ping`` transparently discards
#: stale connections and ``pool_recycle`` caps connection lifetime so the
#: server never serves a dead socket.
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


class Base(DeclarativeBase):
    """Declarative base for all ORM models in the project.

    All feature models subclass this so they share a single metadata registry
    (which Alembic introspects to autogenerate migrations).
    """


class TimestampMixin:
    """Adds ``created_at`` / ``updated_at`` audit columns to a model.

    Mix this in alongside :class:`Base` (``class Foo(Base, TimestampMixin)``) for
    any table that should track row creation and last-modification times. Both
    columns are timezone-aware and populated by the database server clock, so
    timestamps are consistent regardless of which worker writes the row.

    Attributes:
        created_at: Server-set timestamp of row insertion.
        updated_at: Server-set timestamp of insertion, refreshed on every update.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a transactional :class:`AsyncSession` for a single request.

    Intended for use as a FastAPI dependency. The session is opened inside a
    transaction that commits automatically when the request handler returns
    cleanly, rolls back if it raises, and is always closed afterwards.

    Yields:
        An :class:`AsyncSession` bound to an open transaction.
    """
    async with async_session() as session:
        async with session.begin():
            yield session


async def check_db_connection() -> bool:
    """Verify the database is reachable by issuing ``SELECT 1``.

    Used by the application's health-check endpoint. Never raises — any
    connectivity or driver error is reported as a ``False`` result.

    Returns:
        ``True`` if the query succeeds, ``False`` otherwise.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True


__all__ = [
    "engine",
    "async_session",
    "Base",
    "TimestampMixin",
    "get_db",
    "check_db_connection",
]
