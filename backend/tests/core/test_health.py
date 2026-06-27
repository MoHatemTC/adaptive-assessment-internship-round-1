"""Tests for the root health endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_reports_db_and_qdrant_disabled():
    with (
        patch("app.main.check_db_connection", new=AsyncMock(return_value=True)),
        patch("app.main.is_qdrant_configured", return_value=False),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": True, "qdrant": None}


@pytest.mark.asyncio
async def test_health_reports_qdrant_reachable():
    with (
        patch("app.main.check_db_connection", new=AsyncMock(return_value=True)),
        patch("app.main.is_qdrant_configured", return_value=True),
        patch("app.main.check_qdrant_connection", new=AsyncMock(return_value=True)),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": True, "qdrant": True}
