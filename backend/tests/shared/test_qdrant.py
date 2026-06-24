"""Unit tests for Qdrant client factory and collection bootstrap."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.shared import qdrant as qdrant_module
from app.shared.qdrant import COLLECTION_PLATFORM_MEMORY, ensure_collections_exist, get_qdrant_client


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

    with patch("app.shared.qdrant.get_qdrant_client", return_value=mock_client):
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

    with patch("app.shared.qdrant.get_qdrant_client", return_value=mock_client):
        await ensure_collections_exist()

    mock_client.create_collection.assert_not_awaited()
