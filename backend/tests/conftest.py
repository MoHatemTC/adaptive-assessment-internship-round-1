from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings
from app.core import database as _database
from app.main import app as fastapi_app

# Rebind before any test module imports ``engine`` / ``async_session`` so every
# async DB test shares a NullPool engine on pytest's session-scoped event loop.
_test_engine = create_async_engine(
    get_settings().DATABASE_URL,
    poolclass=NullPool,
    pool_pre_ping=True,
)
_database.engine = _test_engine
_database.async_session = async_sessionmaker(
    _test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

from app.core.database import get_db  # noqa: E402


class _DummyAsyncSession:
    """Minimal AsyncSession stub for FastAPI dependency overrides in tests.

    The code-feature API tests patch all service-layer DB work, but the
    `get_db` dependency still needs a commit/rollback/close-capable object.
    """

    async def commit(self) -> None:  # noqa: D102
        return

    async def rollback(self) -> None:  # noqa: D102
        return

    async def close(self) -> None:  # noqa: D102
        return


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _close_test_database() -> AsyncGenerator[None, None]:
    yield
    await _test_engine.dispose()


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """HTTP client for async API tests."""

    async def _override_get_db() -> AsyncGenerator[object, None]:
        session = _DummyAsyncSession()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    fastapi_app.dependency_overrides[get_db] = _override_get_db

    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        try:
            yield ac
        finally:
            fastapi_app.dependency_overrides.pop(get_db, None)
