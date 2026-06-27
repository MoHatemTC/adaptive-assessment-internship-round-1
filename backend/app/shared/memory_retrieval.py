"""Retrieve semantically similar memory cards from Qdrant for adaptation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.config import get_settings
from app.core.logging import get_logger
from app.shared.embedder import embed_text
from app.shared.qdrant import get_qdrant_client, is_qdrant_configured

logger = get_logger(__name__)


@dataclass(frozen=True)
class RetrievedMemory:
    """One memory hit from Qdrant ``platform_memory``."""

    evidence_summary: str
    tool_type: str
    question_index: int
    difficulty: str
    passed: bool
    score: float


async def retrieve_relevant_memories(
    session_id: str,
    query_text: str,
    *,
    limit: int = 5,
    tool_type: str | None = None,
) -> list[RetrievedMemory]:
    """Semantic search over stored evidence for a session.

    Non-critical: returns an empty list when Qdrant is unavailable, the
    collection is empty, or embedding fails.

    Args:
        session_id: Platform assessment session UUID (payload filter).
        query_text: Natural-language query embedded for vector search.
        limit: Maximum number of hits to return.
        tool_type: Optional filter (e.g. ``"voice"``, ``"coding"``).

    Returns:
        Hits ordered by similarity score (highest first).
    """
    settings = get_settings()
    if not is_qdrant_configured():
        logger.warning(
            "qdrant_memory_retrieval_disabled",
            session_id=session_id,
            reason="QDRANT_URL is empty — returning no memories",
        )
        return []

    query = (query_text or "").strip()
    if not query:
        return []

    try:
        vector = await asyncio.to_thread(embed_text, query)
        conditions = [
            FieldCondition(
                key="session_id",
                match=MatchValue(value=session_id),
            )
        ]
        if tool_type:
            conditions.append(
                FieldCondition(
                    key="tool_type",
                    match=MatchValue(value=tool_type),
                )
            )

        client = get_qdrant_client()
        response = await client.query_points(
            collection_name=settings.QDRANT_COLLECTION,
            query=vector,
            query_filter=Filter(must=conditions),
            limit=limit,
            with_payload=True,
        )
        results = response.points or []

        hits: list[RetrievedMemory] = []
        for point in results:
            payload = point.payload or {}
            summary = str(payload.get("evidence_summary", "")).strip()
            if not summary:
                continue
            hits.append(
                RetrievedMemory(
                    evidence_summary=summary,
                    tool_type=str(payload.get("tool_type", "")),
                    question_index=int(payload.get("question_index", 0)),
                    difficulty=str(payload.get("difficulty", "")),
                    passed=bool(payload.get("passed", False)),
                    score=float(point.score or 0.0),
                )
            )

        logger.info(
            "qdrant_memory_retrieved",
            session_id=session_id,
            hit_count=len(hits),
            tool_type=tool_type,
        )
        return hits

    except Exception as exc:  # noqa: BLE001 - retrieval is non-critical
        logger.warning(
            "qdrant_memory_retrieval_failed",
            session_id=session_id,
            reason=str(exc),
        )
        return []


def format_retrieval_context(memories: list[RetrievedMemory]) -> str:
    """Turn Qdrant hits into a short block for adaptation prompts."""
    if not memories:
        return ""

    lines = [
        (
            f"- [{item.tool_type} Q{item.question_index}, {item.difficulty}] "
            f"{item.evidence_summary}"
        )
        for item in memories
    ]
    return "Semantically relevant prior evidence:\n" + "\n".join(lines)


async def enrich_memory_summary_for_adaptation(
    session_id: str,
    base_summary: str,
    query_text: str,
    *,
    tool_type: str | None = None,
    limit: int = 5,
) -> str:
    """Append Qdrant retrieval context to a narrative memory summary.

    Args:
        session_id: Owning assessment session UUID.
        base_summary: Summary from the memory agent or adaptation layer.
        query_text: Embedding query describing what to retrieve.
        tool_type: Optional tool filter; ``None`` searches all tools in session.
        limit: Max Qdrant hits.

    Returns:
        ``base_summary`` unchanged when retrieval yields nothing; otherwise
        base summary plus a formatted evidence block.
    """
    memories = await retrieve_relevant_memories(
        session_id,
        query_text,
        limit=limit,
        tool_type=tool_type,
    )
    context = format_retrieval_context(memories)
    if not context:
        return base_summary
    if not base_summary.strip():
        return context
    return f"{base_summary.strip()}\n\n{context}"


__all__ = [
    "RetrievedMemory",
    "enrich_memory_summary_for_adaptation",
    "format_retrieval_context",
    "retrieve_relevant_memories",
]
