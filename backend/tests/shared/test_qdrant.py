"""Unit tests for Qdrant client factory and collection bootstrap."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.shared import qdrant as qdrant_module
from app.shared.qdrant import (
    COLLECTION_PLATFORM_MEMORY,
    bootstrap_qdrant,
    check_qdrant_connection,
    ensure_collections_exist,
    get_qdrant_client,
    is_qdrant_configured,
)


@pytest.fixture(autouse=True)
def _reset_qdrant_singleton():
    qdrant_module._client = None
    yield
    qdrant_module._client = None


def test_get_qdrant_client_returns_singleton():
    mock_client = MagicMock()
    with patch("app.shared.qdrant.AsyncQdrantClient", return_value=mock_client) as factory:
        first = get_qdrant_client()
        second = get_qdrant_client()
    assert first is second
    factory.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_collections_exist_creates_missing_collection():
    mock_client = AsyncMock()
    existing = MagicMock()
    existing.collections = []
    mock_client.get_collections.return_value = existing

    with (
        patch("app.shared.qdrant.is_qdrant_configured", return_value=True),
        patch("app.shared.qdrant.get_qdrant_client", return_value=mock_client),
    ):
        await ensure_collections_exist()

    mock_client.create_collection.assert_awaited_once()
    call_kwargs = mock_client.create_collection.await_args.kwargs
    assert call_kwargs["collection_name"] == COLLECTION_PLATFORM_MEMORY


@pytest.mark.asyncio
async def test_ensure_collections_exist_skips_when_present():
    mock_client = AsyncMock()
    existing = MagicMock()
    collection = MagicMock()
    collection.name = COLLECTION_PLATFORM_MEMORY
    existing.collections = [collection]
    mock_client.get_collections.return_value = existing

    with (
        patch("app.shared.qdrant.is_qdrant_configured", return_value=True),
        patch("app.shared.qdrant.get_qdrant_client", return_value=mock_client),
    ):
        await ensure_collections_exist()

    mock_client.create_collection.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_collections_exist_warns_when_url_missing():
    with (
        patch("app.shared.qdrant.is_qdrant_configured", return_value=False),
        patch("app.shared.qdrant.get_qdrant_client") as mock_factory,
    ):
        await ensure_collections_exist()
    mock_factory.assert_not_called()


@pytest.mark.asyncio
async def test_check_qdrant_connection_false_when_not_configured():
    with patch("app.shared.qdrant.is_qdrant_configured", return_value=False):
        assert await check_qdrant_connection() is False


@pytest.mark.asyncio
async def test_check_qdrant_connection_true_when_collection_reachable():
    mock_client = AsyncMock()
    mock_client.get_collection = AsyncMock()
    with (
        patch("app.shared.qdrant.is_qdrant_configured", return_value=True),
        patch("app.shared.qdrant.get_qdrant_client", return_value=mock_client),
        patch("app.shared.qdrant.get_settings") as mock_settings,
    ):
        mock_settings.return_value.QDRANT_COLLECTION = COLLECTION_PLATFORM_MEMORY
        assert await check_qdrant_connection() is True


@pytest.mark.asyncio
async def test_bootstrap_qdrant_returns_false_when_not_configured():
    with patch("app.shared.qdrant.is_qdrant_configured", return_value=False):
        assert await bootstrap_qdrant() is False
