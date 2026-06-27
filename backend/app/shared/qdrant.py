"""Qdrant Cloud async client factory and collection bootstrap."""

from __future__ import annotations

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

COLLECTION_PLATFORM_MEMORY = "platform_memory"
VECTOR_SIZE = 384  # all-MiniLM-L6-v2 compatible
_PAYLOAD_INDEX_FIELDS = ("session_id", "tool_type")

_client: AsyncQdrantClient | None = None


def is_qdrant_configured() -> bool:
    """Return whether Qdrant Cloud URL is set (memory features enabled)."""
    return bool(get_settings().QDRANT_URL.strip())


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


async def _ensure_payload_indexes(client: AsyncQdrantClient, collection_name: str) -> None:
    """Create keyword indexes required for filtered memory retrieval on Qdrant Cloud."""
    for field_name in _PAYLOAD_INDEX_FIELDS:
        try:
            await client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=PayloadSchemaType.KEYWORD,
            )
            logger.info("qdrant_payload_index_created", collection=collection_name, field=field_name)
        except Exception as exc:  # noqa: BLE001 - index may already exist
            logger.debug(
                "qdrant_payload_index_skipped",
                collection=collection_name,
                field=field_name,
                reason=str(exc),
            )


async def ensure_collections_exist() -> None:
    """Create required Qdrant collections if they do not exist."""
    if not is_qdrant_configured():
        logger.warning(
            "qdrant_not_configured",
            reason="QDRANT_URL is empty — skipping collection bootstrap",
        )
        return

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

    await _ensure_payload_indexes(client, COLLECTION_PLATFORM_MEMORY)


async def check_qdrant_connection() -> bool:
    """Ping the configured Qdrant collection. Returns False when not configured."""
    if not is_qdrant_configured():
        return False

    settings = get_settings()
    try:
        client = get_qdrant_client()
        await client.get_collection(settings.QDRANT_COLLECTION)
        return True
    except Exception as exc:  # noqa: BLE001 - health probe must not raise
        logger.warning(
            "qdrant_connection_failed",
            collection=settings.QDRANT_COLLECTION,
            reason=str(exc),
        )
        return False


async def bootstrap_qdrant() -> bool:
    """Ensure Qdrant is ready at startup. Non-blocking: logs and returns status."""
    if not is_qdrant_configured():
        logger.warning(
            "qdrant_not_configured",
            reason=(
                "QDRANT_URL is empty — memory card storage and semantic "
                "retrieval are disabled"
            ),
        )
        return False

    try:
        await ensure_collections_exist()
    except Exception as exc:  # noqa: BLE001 - startup must continue
        logger.warning("qdrant_startup_failed", reason=str(exc))
        return False

    if await check_qdrant_connection():
        settings = get_settings()
        logger.info(
            "qdrant_startup_ok",
            collection=settings.QDRANT_COLLECTION,
            url_host=settings.QDRANT_URL.split("://", 1)[-1].split("/", 1)[0],
        )
        return True

    logger.warning(
        "qdrant_startup_unreachable",
        reason="configured Qdrant URL did not respond to collection info",
    )
    return False
