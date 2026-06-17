from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from app.core.database import get_db
from app.main import app as fastapi_app


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
