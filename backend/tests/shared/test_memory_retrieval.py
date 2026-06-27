"""Tests for Qdrant memory retrieval used in adaptation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.shared.memory_retrieval import (
    RetrievedMemory,
    enrich_memory_summary_for_adaptation,
    format_retrieval_context,
    retrieve_relevant_memories,
)


def test_format_retrieval_context_empty():
    assert format_retrieval_context([]) == ""


def test_format_retrieval_context_formats_lines():
    memories = [
        RetrievedMemory(
            evidence_summary="Explained debugging clearly.",
            tool_type="voice",
            question_index=0,
            difficulty="intermediate",
            passed=True,
            score=0.91,
        )
    ]
    text = format_retrieval_context(memories)
    assert "Semantically relevant prior evidence:" in text
    assert "[voice Q0, intermediate]" in text
    assert "Explained debugging clearly." in text


@pytest.mark.asyncio
async def test_retrieve_returns_empty_when_qdrant_url_missing():
    with patch("app.shared.memory_retrieval.get_settings") as mock_settings:
        mock_settings.return_value.QDRANT_URL = ""
        mock_settings.return_value.QDRANT_COLLECTION = "platform_memory"
        hits = await retrieve_relevant_memories("sess-1", "focus on thinking")
    assert hits == []


@pytest.mark.asyncio
async def test_retrieve_returns_hits_from_qdrant():
    point = MagicMock()
    point.score = 0.88
    point.payload = {
        "evidence_summary": "Strong system design reasoning.",
        "tool_type": "voice",
        "question_index": 1,
        "difficulty": "advanced",
        "passed": True,
    }

    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.points = [point]
    mock_client.query_points = AsyncMock(return_value=mock_response)

    with (
        patch("app.shared.memory_retrieval.get_settings") as mock_settings,
        patch(
            "app.shared.memory_retrieval.asyncio.to_thread",
            new=AsyncMock(return_value=[0.1] * 384),
        ),
        patch(
            "app.shared.memory_retrieval.get_qdrant_client",
            return_value=mock_client,
        ),
    ):
        mock_settings.return_value.QDRANT_URL = "http://qdrant.test"
        mock_settings.return_value.QDRANT_COLLECTION = "platform_memory"
        hits = await retrieve_relevant_memories("sess-1", "system design")

    assert len(hits) == 1
    assert hits[0].evidence_summary == "Strong system design reasoning."
    mock_client.query_points.assert_awaited_once()


@pytest.mark.asyncio
async def test_enrich_memory_summary_appends_context():
    with patch(
        "app.shared.memory_retrieval.retrieve_relevant_memories",
        new=AsyncMock(
            return_value=[
                RetrievedMemory(
                    evidence_summary="Needs more depth on APIs.",
                    tool_type="coding",
                    question_index=2,
                    difficulty="intermediate",
                    passed=False,
                    score=0.75,
                )
            ]
        ),
    ):
        enriched = await enrich_memory_summary_for_adaptation(
            "sess-1",
            "Base summary.",
            "next API question",
        )

    assert enriched.startswith("Base summary.")
    assert "Semantically relevant prior evidence:" in enriched
    assert "Needs more depth on APIs." in enriched


@pytest.mark.asyncio
async def test_enrich_memory_summary_returns_base_when_no_hits():
    with patch(
        "app.shared.memory_retrieval.retrieve_relevant_memories",
        new=AsyncMock(return_value=[]),
    ):
        enriched = await enrich_memory_summary_for_adaptation(
            "sess-1",
            "Only base.",
            "query",
        )
    assert enriched == "Only base."
