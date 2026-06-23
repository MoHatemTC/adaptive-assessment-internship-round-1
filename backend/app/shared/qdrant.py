"""Qdrant Cloud async client factory and collection bootstrap."""

from __future__ import annotations

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

COLLECTION_PLATFORM_MEMORY = "platform_memory"
VECTOR_SIZE = 384  # all-MiniLM-L6-v2 compatible

_client: AsyncQdrantClient | None = None


def get_qdrant_client() -> AsyncQdrantClient:
    """Return the singleton Qdrant async client."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncQdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
        )
    return _client


async def ensure_collections_exist() -> None:
    """Create required Qdrant collections if they do not exist."""
    client = get_qdrant_client()
    existing = await client.get_collections()
    existing_names = {c.name for c in existing.collections}

    if COLLECTION_PLATFORM_MEMORY not in existing_names:
        await client.create_collection(
            collection_name=COLLECTION_PLATFORM_MEMORY,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE,
            ),
        )
        logger.info(
            "qdrant_collection_created",
            collection=COLLECTION_PLATFORM_MEMORY,
        )
    else:
        logger.info(
            "qdrant_collection_exists",
            collection=COLLECTION_PLATFORM_MEMORY,
        )
