"""Tests for the voice analysis (Layer 7) and adaptation (Layer 8) layers.

DB access and LLM calls are mocked so the suite runs without a live database or
API key, mirroring the mock patterns in test_voice_evaluation.py.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.voice.adaptation import (
    _select_next_difficulty,
    generate_next_voice_question,
)
from app.features.voice.analysis import analyze_voice_session

_ANALYSIS = "app.features.voice.analysis"
_ADAPT = "app.features.voice.adaptation"


@pytest.fixture
def analysis_result() -> dict:
    """A realistic analysis dict as returned by analyze_voice_session."""
    return {
        "session_id": "test-session-uuid",
        "total_cards": 3,
        "dimensions": {
            "thinking": {"signal_count": 2, "total": 3, "rate": 0.67},
            "soft": {"signal_count": 1, "total": 3, "rate": 0.33},
            "work": {"signal_count": 3, "total": 3, "rate": 1.0},
            "digital_ai": {"signal_count": 0, "total": 3, "rate": 0.0},
            "growth": {"signal_count": 2, "total": 3, "rate": 0.67},
        },
        "weakest_dimension": "digital_ai",
        "strongest_dimension": "work",
        "mastery_level": "medium",
        "recommended_follow_up_depth": "simple",
    }


def _make_session_mock(mock_db: AsyncMock) -> MagicMock:
    """Return an async-context-manager mock that yields mock_db."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_db)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


def _mock_card(signals: dict, passed: bool) -> MagicMock:
    """Return a mock voice MemoryCard ORM row."""
    card = MagicMock()
    card.dimension_signals = json.dumps(signals)
    card.passed = passed
    return card


def _cards_db(cards: list) -> AsyncMock:
    """Return a mock db whose ``execute`` yields the given memory cards."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = cards
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    return mock_db


def _signals(**overrides: bool) -> dict:
    """Build a dimension_signals dict, all False unless overridden."""
    base = {
        "thinking": False,
        "soft": False,
        "work": False,
        "digital_ai": False,
        "growth": False,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Test 1 — empty session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze_returns_empty_result_when_no_cards():
    mock_db = _cards_db([])

    with patch(f"{_ANALYSIS}.async_session", return_value=_make_session_mock(mock_db)):
        result = await analyze_voice_session("session-x", 0)

    assert result["total_cards"] == 0
    assert result["mastery_level"] == "low"


# ---------------------------------------------------------------------------
# Test 2 — dimension rates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze_computes_correct_dimension_rates():
    cards = [_mock_card(_signals(thinking=True), passed=True) for _ in range(3)]
    mock_db = _cards_db(cards)

    with patch(f"{_ANALYSIS}.async_session", return_value=_make_session_mock(mock_db)):
        result = await analyze_voice_session("session-x", 0)

    assert result["dimensions"]["thinking"]["rate"] == 1.0
    assert result["dimensions"]["soft"]["rate"] == 0.0


# ---------------------------------------------------------------------------
# Test 3 — weakest dimension
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze_identifies_weakest_dimension():
    # Every dimension engaged except digital_ai, which stays at rate 0.0.
    cards = [
        _mock_card(
            _signals(thinking=True, soft=True, work=True, growth=True),
            passed=True,
        )
        for _ in range(3)
    ]
    mock_db = _cards_db(cards)

    with patch(f"{_ANALYSIS}.async_session", return_value=_make_session_mock(mock_db)):
        result = await analyze_voice_session("session-x", 0)

    assert result["weakest_dimension"] == "digital_ai"


# ---------------------------------------------------------------------------
# Test 4 — high mastery when all passed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze_mastery_high_when_all_passed():
    cards = [_mock_card(_signals(thinking=True), passed=True) for _ in range(3)]
    mock_db = _cards_db(cards)

    with patch(f"{_ANALYSIS}.async_session", return_value=_make_session_mock(mock_db)):
        result = await analyze_voice_session("session-x", 0)

    assert result["mastery_level"] == "high"
    assert result["recommended_follow_up_depth"] == "deep"


# ---------------------------------------------------------------------------
# Test 5 — low mastery when none passed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze_mastery_low_when_none_passed():
    cards = [_mock_card(_signals(thinking=True), passed=False) for _ in range(3)]
    mock_db = _cards_db(cards)

    with patch(f"{_ANALYSIS}.async_session", return_value=_make_session_mock(mock_db)):
        result = await analyze_voice_session("session-x", 0)

    assert result["mastery_level"] == "low"
    assert result["recommended_follow_up_depth"] == "simple"


# ---------------------------------------------------------------------------
# Test 6 — difficulty increases on high mastery
# ---------------------------------------------------------------------------

def test_select_next_difficulty_increases_on_high_mastery():
    assert _select_next_difficulty("beginner", "high", {}) == "intermediate"
    assert _select_next_difficulty("intermediate", "high", {}) == "advanced"


# ---------------------------------------------------------------------------
# Test 7 — difficulty capped at admin max
# ---------------------------------------------------------------------------

def test_select_next_difficulty_caps_at_admin_max():
    assert (
        _select_next_difficulty(
            "advanced", "high", {"max_difficulty": "intermediate"}
        )
        == "intermediate"
    )


# ---------------------------------------------------------------------------
# Test 8 — question generation falls back on LLM failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_next_question_fallback_on_llm_failure(analysis_result):
    with patch(f"{_ADAPT}.get_llm", side_effect=RuntimeError("LLM unavailable")):
        result = await generate_next_voice_question(
            analysis_result, {}, {}, "beginner", 0, ""
        )

    question_text, next_diff, depth = result
    assert isinstance(question_text, str)
    assert len(question_text) > 10
    assert next_diff in ["beginner", "intermediate", "advanced"]


# ---------------------------------------------------------------------------
# Test 9 — cold start (no memory cards yet) yields low mastery
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cold_start_returns_low_mastery():
    mock_db = _cards_db([])

    with patch(f"{_ANALYSIS}.async_session", return_value=_make_session_mock(mock_db)):
        result = await analyze_voice_session("cold-start-session", 0)

    assert result["mastery_level"] == "low"
    assert result["total_cards"] == 0
    assert result["weakest_dimension"] is None
    assert result["prior_questions"] == []


# ---------------------------------------------------------------------------
# Test 10 — difficulty selection respects floor and admin ceiling
# ---------------------------------------------------------------------------

def test_difficulty_bounds_respected():
    # Min bound: already at beginner with low mastery — cannot go below.
    assert _select_next_difficulty("beginner", "low", {}) == "beginner"
    # Max bound: admin caps at intermediate, high mastery from advanced.
    assert (
        _select_next_difficulty(
            "advanced", "high", {"max_difficulty": "intermediate"}
        )
        == "intermediate"
    )
    # Max bound: already at admin max with high mastery — stays at max.
    assert (
        _select_next_difficulty(
            "intermediate", "high", {"max_difficulty": "intermediate"}
        )
        == "intermediate"
    )
