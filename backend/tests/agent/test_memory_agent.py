"""Tests for the Memory Agent (Layer 6).

Each test exercises a single node in isolation, mocking DB access and LLM
calls so the suite runs without a live database or API key.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.memory_agent import (
    MemoryAgentState,
    build_memory_graph,
    extract_card_node,
    load_prior_cards_node,
    save_card_node,
    summarize_memory_node,
)
from app.shared.schemas.memory import (
    DimensionSignals,
    MemoryCardCreate,
    MemoryCardRead,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_SESSION_ID = "test-session-uuid-1234"
_NOW = datetime(2026, 1, 1, 12, 0, 0)


@pytest.fixture
def base_state() -> MemoryAgentState:
    """Minimal valid state for each node test."""
    return {
        "session_id": _SESSION_ID,
        "tool_type": "mcq",
        "question_index": 0,
        "question_text": "What is a REST API?",
        "learner_response": "A REST API uses HTTP methods to expose resources.",
        "rubric_scores_json": (
            '{"dimensions":[{"name":"thinking","score":0.8,"feedback":"Good"}],"overall":0.8}'
        ),
        "passed": True,
        "difficulty": "intermediate",
        "prior_cards": [],
        "card_create": None,
        "new_card": None,
        "memory_summary": "",
        "error": None,
    }


def _make_session_mock(mock_db: AsyncMock) -> MagicMock:
    """Return a context-manager mock that yields mock_db."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_db)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


def _mock_card_row(
    card_id: int,
    question_index: int,
    dimension_signals_dict: dict,
    passed: bool = True,
    difficulty: str = "intermediate",
) -> MagicMock:
    """Return a mock MemoryCard ORM row with consistent field values."""
    row = MagicMock()
    row.id = card_id
    row.session_id = _SESSION_ID
    row.tool_type = "mcq"
    row.question_index = question_index
    row.difficulty = difficulty
    row.evidence_summary = f"Evidence for question {question_index}."
    row.dimension_signals = json.dumps(dimension_signals_dict)
    row.passed = passed
    row.created_at = _NOW
    return row


def _all_false_signals() -> dict:
    return {
        "thinking": False, "soft": False, "work": False,
        "digital_ai": False, "growth": False,
    }


# ---------------------------------------------------------------------------
# Test 1 — load_prior_cards_node: empty session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_load_prior_cards_returns_empty_for_new_session(base_state):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch(
        "app.agent.memory_agent.async_session",
        return_value=_make_session_mock(mock_db),
    ):
        result = await load_prior_cards_node(base_state)

    assert result["prior_cards"] == []
    assert "error" not in result


# ---------------------------------------------------------------------------
# Test 2 — load_prior_cards_node: two existing cards
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_load_prior_cards_returns_existing_cards(base_state):
    signals_q0 = {
        "thinking": True, "soft": False, "work": False,
        "digital_ai": False, "growth": False,
    }
    signals_q1 = {
        "thinking": False, "soft": True, "work": False,
        "digital_ai": False, "growth": False,
    }

    row0 = _mock_card_row(
        card_id=1, question_index=0, dimension_signals_dict=signals_q0
    )
    row1 = _mock_card_row(
        card_id=2, question_index=1, dimension_signals_dict=signals_q1, passed=False
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [row0, row1]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch(
        "app.agent.memory_agent.async_session",
        return_value=_make_session_mock(mock_db),
    ):
        result = await load_prior_cards_node(base_state)

    cards = result["prior_cards"]
    assert len(cards) == 2
    assert cards[0]["question_index"] == 0
    assert cards[0]["dimension_signals"]["thinking"] is True
    assert cards[1]["question_index"] == 1
    assert cards[1]["passed"] is False
    assert "error" not in result


# ---------------------------------------------------------------------------
# Test 3 — extract_card_node: valid LLM response
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_card_produces_valid_card_create(base_state):
    llm_json = json.dumps({
        "evidence_summary": "Learner demonstrates solid REST API understanding.",
        "dimension_signals": {
            "thinking": True,
            "soft": False,
            "work": False,
            "digital_ai": False,
            "growth": False,
        },
    })

    mock_response = MagicMock()
    mock_response.content = llm_json
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    with patch(
        "app.agent.memory_agent.get_llm_with_tracing",
        return_value=(mock_llm, []),
    ):
        result = await extract_card_node(base_state)

    assert "card_create" in result
    card = result["card_create"]
    expected_evidence = "Learner demonstrates solid REST API understanding."
    assert card["evidence_summary"] == expected_evidence
    assert card["dimension_signals"]["thinking"] is True
    assert card["session_id"] == _SESSION_ID
    assert card["passed"] is True
    assert "error" not in result


# ---------------------------------------------------------------------------
# Test 4 — extract_card_node: skip when state already has an error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_card_skips_when_error_in_state(base_state):
    base_state["error"] = "prior node failure"

    with patch("app.agent.memory_agent.get_llm_with_tracing") as mock_factory:
        result = await extract_card_node(base_state)

    assert result == {}
    mock_factory.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5 — extract_card_node: malformed LLM response sets error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_card_handles_malformed_llm_response(base_state):
    mock_response = MagicMock()
    mock_response.content = "not valid json %%%"
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    with patch(
        "app.agent.memory_agent.get_llm_with_tracing",
        return_value=(mock_llm, []),
    ):
        result = await extract_card_node(base_state)

    assert "error" in result
    assert "card_create" not in result


# ---------------------------------------------------------------------------
# Test 6 — save_card_node: persists and returns new_card
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_save_card_persists_to_db(base_state):
    card_create = MemoryCardCreate(
        session_id=_SESSION_ID,
        tool_type="mcq",
        question_index=0,
        difficulty="intermediate",
        evidence_summary="Solid REST understanding.",
        dimension_signals=DimensionSignals(thinking=True),
        passed=True,
    )
    base_state["card_create"] = card_create.model_dump(mode="json")

    async def _mock_refresh(obj: object) -> None:
        obj.id = 1  # type: ignore[attr-defined]
        obj.created_at = _NOW  # type: ignore[attr-defined]

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock(side_effect=_mock_refresh)

    with patch(
        "app.agent.memory_agent.async_session",
        return_value=_make_session_mock(mock_db),
    ):
        result = await save_card_node(base_state)

    assert "new_card" in result
    new_card = result["new_card"]
    assert new_card["id"] == 1
    assert new_card["session_id"] == _SESSION_ID
    assert new_card["evidence_summary"] == "Solid REST understanding."
    assert new_card["dimension_signals"]["thinking"] is True
    mock_db.add.assert_called_once()
    mock_db.commit.assert_awaited_once()
    mock_db.refresh.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 7 — summarize_memory_node: produces non-empty summary text
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summarize_memory_produces_text(base_state):
    prior_card = MemoryCardRead(
        id=1,
        session_id=_SESSION_ID,
        tool_type="mcq",
        question_index=0,
        difficulty="intermediate",
        evidence_summary="Learner shows strong logical reasoning.",
        dimension_signals=DimensionSignals(thinking=True),
        passed=True,
        created_at=_NOW,
    ).model_dump(mode="json")

    new_card = MemoryCardRead(
        id=2,
        session_id=_SESSION_ID,
        tool_type="voice",
        question_index=1,
        difficulty="advanced",
        evidence_summary="Learner struggles with verbal articulation.",
        dimension_signals=DimensionSignals(soft=False),
        passed=False,
        created_at=_NOW,
    ).model_dump(mode="json")

    base_state["prior_cards"] = [prior_card]
    base_state["new_card"] = new_card

    expected_summary = "Learner shows reasoning strength; needs work on communication."
    mock_response = MagicMock()
    mock_response.content = expected_summary
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    with patch(
        "app.agent.memory_agent.get_llm_with_tracing",
        return_value=(mock_llm, []),
    ):
        result = await summarize_memory_node(base_state)

    assert result["memory_summary"] == expected_summary


# ---------------------------------------------------------------------------
# Test 8 — summarize_memory_node: skip when state already has an error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summarize_memory_skips_when_error_in_state(base_state):
    base_state["error"] = "pipeline failed upstream"

    with patch("app.agent.memory_agent.get_llm_with_tracing") as mock_factory:
        result = await summarize_memory_node(base_state)

    assert result["memory_summary"] == ""
    mock_factory.assert_not_called()


# ---------------------------------------------------------------------------
# Bonus: build_memory_graph compiles without error
# ---------------------------------------------------------------------------

def test_build_memory_graph_has_expected_nodes():
    graph = build_memory_graph()
    node_names = set(graph.nodes.keys())
    expected_nodes = {
        "load_prior_cards", "extract_card", "save_card",
        "embed_and_store", "summarize_memory",
    }
    for expected in expected_nodes:
        assert expected in node_names


# ---------------------------------------------------------------------------
# Kimi K2 list-content parsing (Fix 1)
# ---------------------------------------------------------------------------

def test_memory_agent_handles_kimi_k2_list_response():
    """Verify the memory agent parses Kimi K2's list response format.

    Kimi K2 returns a list of thinking blocks followed by the final answer
    string. The helper must extract that final string without crashing on a
    ``.strip()`` of a list.
    """
    from app.agent.memory_agent import _extract_answer_from_response

    kimi_list_response = [
        {"type": "thinking", "thinking": "Let me analyze this learner response..."},
        {"type": "thinking", "thinking": "They seem to understand the concept..."},
        '{"evidence_summary": "Learner showed clear reasoning", '
        '"dimension_signals": {"thinking": true}}',
    ]
    mock_response = MagicMock()
    mock_response.content = kimi_list_response

    answer = _extract_answer_from_response(mock_response)

    assert answer != ""
    assert "evidence_summary" in answer
    assert "clear reasoning" in answer


# ---------------------------------------------------------------------------
# Qdrant wiring is non-critical (Fix 2)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_embed_and_store_node_skips_on_qdrant_failure():
    """If Qdrant is unreachable, the node logs a warning and does NOT set
    ``state['error']`` — the graph must continue to summarize_memory.
    """
    from app.agent.memory_agent import embed_and_store_node

    mock_card = MemoryCardRead(
        id=1,
        session_id="test-session-id-1234567890123",
        tool_type="voice",
        question_index=0,
        difficulty="beginner",
        evidence_summary="Learner demonstrated clear understanding",
        dimension_signals=DimensionSignals(),
        passed=True,
        created_at=_NOW,
    )

    state = {
        "session_id": "test-session-id-1234567890123",
        "saved_card": mock_card,
        "error": None,
    }

    # Mock the embedder so the test does not load the SentenceTransformer model,
    # and force the Qdrant upsert to fail to prove the failure is swallowed.
    with patch(
        "app.shared.embedder.embed_text", return_value=[0.0] * 384
    ), patch("app.shared.qdrant.get_qdrant_client") as mock_client:
        mock_client.return_value.upsert = AsyncMock(
            side_effect=Exception("Qdrant unreachable")
        )
        result = await embed_and_store_node(state)

    # Must not set error — Qdrant is non-critical.
    assert result.get("error") is None
