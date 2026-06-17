"""Alembic migration environment.

Supports both offline (SQL-script) and online (async database) migration modes.
The DATABASE_URL is injected at runtime from :func:`app.config.get_settings` so
no credentials are hard-coded in this file or in ``alembic.ini``.

All application model modules are imported here to ensure their tables are
registered with :attr:`Base.metadata` before Alembic inspects it.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.database import Base
import app.admin.models  # noqa: F401 — registers Assessment with Base.metadata
import app.features.mcq.models  # noqa: F401 — registers MCQ tables
import app.features.voice.models  # noqa: F401 — registers voice tables
import app.proctoring.models  # noqa: F401 — registers ProctoringEvent
import app.sessions.models  # noqa: F401 — registers session/grading tables
import app.features.diagram.models  # noqa: F401 — registers diagram tables
import app.features.code.models  # noqa: F401 — registers coding tables

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode, emitting SQL to stdout.

    In this mode Alembic does not open a real database connection. The URL is
    still injected from settings so the emitted SQL targets the correct dialect.
    """
    from app.config import get_settings

    config.set_main_option("sqlalchemy.url", str(get_settings().DATABASE_URL))
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    from app.config import get_settings

    config.set_main_option("sqlalchemy.url", str(get_settings().DATABASE_URL))
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live async database connection."""
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
