"""Tests for the silent voice evaluation layer (Layers 5+6).

Each test mocks DB access and LLM calls so the suite runs without a live
database or API key, mirroring the mock patterns used in test_voice.py and
test_memory_agent.py.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.voice.evaluation import (
    _detect_flag,
    evaluate_voice_response,
    get_transcript_text,
)
from app.features.voice.schemas import VoiceAdaptiveInput

_EVAL = "app.features.voice.evaluation"


def _patch_traced_llm(mock_llm: AsyncMock):
    """Patch the traced LLM gateway used by voice evaluation."""
    return patch(f"{_EVAL}.get_llm_with_tracing", return_value=(mock_llm, []))


@pytest.fixture
def voice_adaptive_input() -> VoiceAdaptiveInput:
    """Minimal valid evaluation input for a single voice response."""
    return VoiceAdaptiveInput(
        session_id="test-session-uuid-5678",
        voice_session_id=1,
        question_index=0,
        question_text="Explain how you would design a REST API for a payment system.",
        target_difficulty="intermediate",
        learner_profile={
            "name": "Test User",
            "role": "backend_developer",
            "level": "mid",
        },
        admin_config={"max_difficulty": "advanced", "allowed_topics": ["api_design"]},
        follow_up_depth="simple",
    )


def _make_session_mock(mock_db: AsyncMock) -> MagicMock:
    """Return an async-context-manager mock that yields mock_db."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_db)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm


def _mock_transcript_row(
    chunk_index: int,
    transcript_text: str,
    speaker_confidence: float,
) -> MagicMock:
    """Return a mock VoiceTranscript ORM row."""
    row = MagicMock()
    row.chunk_index = chunk_index
    row.transcript_text = transcript_text
    row.speaker_confidence = speaker_confidence
    return row


def _transcript_db(rows: list) -> AsyncMock:
    """Return a mock db whose ``execute`` yields the given transcript rows."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = rows
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    return mock_db


# ---------------------------------------------------------------------------
# Test 1 — get_transcript_text concatenates chunks in order
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_transcript_text_concatenates_in_order():
    rows = [
        _mock_transcript_row(0, "First chunk.", 0.8),
        _mock_transcript_row(1, "Second chunk.", 0.9),
        _mock_transcript_row(2, "Third chunk.", 0.85),
    ]
    mock_db = _transcript_db(rows)

    text, avg = await get_transcript_text(1, mock_db)

    assert "First chunk." in text
    assert "Second chunk." in text
    assert "Third chunk." in text
    assert abs(avg - 0.85) < 0.01


# ---------------------------------------------------------------------------
# Test 2 — get_transcript_text returns ("", 0.0) for empty session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_transcript_text_empty_returns_tuple():
    mock_db = _transcript_db([])

    text, avg = await get_transcript_text(1, mock_db)

    assert text == ""
    assert avg == 0.0


# ---------------------------------------------------------------------------
# Tests 3–6 — _detect_flag priority and thresholds
# ---------------------------------------------------------------------------

def test_detect_flag_timed_out_takes_priority():
    flag = _detect_flag("A full and detailed answer given here.", 0.9, "timed_out")
    assert flag == "timed_out"


def test_detect_flag_empty_transcript():
    flag = _detect_flag("  ", 0.9, "completed")
    assert flag == "empty_transcript"


def test_detect_flag_low_confidence():
    flag = _detect_flag(
        "A full and detailed answer given here clearly.", 0.55, "completed"
    )
    assert flag == "low_confidence"


def test_detect_flag_clean_response_returns_none():
    flag = _detect_flag(
        "I would design using REST principles, stateless requests, JWT auth.",
        0.82,
        "completed",
    )
    assert flag is None


# ---------------------------------------------------------------------------
# Test 7 — flagged session never invokes the LLM
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evaluate_flagged_session_never_calls_llm(voice_adaptive_input):
    voice_session = MagicMock()
    voice_session.id = 1
    voice_session.status = "timed_out"

    async def _refresh(obj: object) -> None:
        obj.id = 10  # type: ignore[attr-defined]

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=voice_session)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock(side_effect=_refresh)

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock()

    tracing_mock = MagicMock(return_value=(mock_llm, []))

    with (
        patch(f"{_EVAL}.async_session", return_value=_make_session_mock(mock_db)),
        patch(f"{_EVAL}.get_transcript_text", AsyncMock(return_value=("", 0.0))),
        patch(f"{_EVAL}.run_memory_agent", AsyncMock(return_value=(None, ""))),
        patch(f"{_EVAL}.get_llm_with_tracing", tracing_mock),
    ):
        result = await evaluate_voice_response(voice_adaptive_input)

    assert result.flagged is True
    assert result.flag_reason == "timed_out"
    assert result.memory_summary == ""
    tracing_mock.assert_not_called()
    mock_llm.ainvoke.assert_not_called()


# ---------------------------------------------------------------------------
# Test 8 — clean response is graded, stored, and remembered
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evaluate_clean_response_grades_and_stores(voice_adaptive_input):
    voice_session = MagicMock()
    voice_session.id = 1
    voice_session.status = "completed"

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=voice_session)
    mock_db.add = MagicMock()  # SQLAlchemy add() is synchronous

    rubric_json = json.dumps(
        {
            "dimensions": [
                {"name": "thinking", "score": 0.8, "feedback": "Clear reasoning."},
                {"name": "soft", "score": 0.6, "feedback": "Well articulated."},
                {"name": "work", "score": 0.7, "feedback": "Concrete design."},
                {"name": "growth", "score": 0.5, "feedback": "Open to iteration."},
            ],
            "overall": 0.8,
        }
    )
    mock_response = MagicMock()
    mock_response.content = rubric_json
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    mock_card = MagicMock()
    mock_card.id = 7

    with (
        patch(f"{_EVAL}.async_session", return_value=_make_session_mock(mock_db)),
        patch(
            f"{_EVAL}.get_transcript_text",
            AsyncMock(return_value=("I would use RESTful endpoints with JWT.", 0.85)),
        ),
        _patch_traced_llm(mock_llm),
        patch(f"{_EVAL}._write_grade_result", AsyncMock(return_value=42)),
        patch(
            f"{_EVAL}.run_memory_agent",
            AsyncMock(return_value=(mock_card, "Strong API knowledge demonstrated.")),
        ),
    ):
        result = await evaluate_voice_response(voice_adaptive_input)

    assert result.flagged is False
    assert result.grade_result_id == 42
    assert result.memory_card_id == 7
    assert result.memory_summary == "Strong API knowledge demonstrated."
    mock_llm.ainvoke.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 9 — flagged session skips memory extraction entirely
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_flagged_session_skips_memory_extraction(voice_adaptive_input):
    voice_session = MagicMock()
    voice_session.id = 1
    voice_session.status = "timed_out"

    async def _refresh(obj: object) -> None:
        obj.id = 10  # type: ignore[attr-defined]

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=voice_session)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock(side_effect=_refresh)

    mock_memory_agent = AsyncMock(return_value=(MagicMock(), "should never appear"))

    with (
        patch(f"{_EVAL}.async_session", return_value=_make_session_mock(mock_db)),
        patch(f"{_EVAL}.get_transcript_text", AsyncMock(return_value=("", 0.0))),
        patch(f"{_EVAL}.run_memory_agent", mock_memory_agent),
    ):
        result = await evaluate_voice_response(voice_adaptive_input)

    mock_memory_agent.assert_not_called()
    assert result.memory_summary == ""
    assert result.memory_card_id is None


# ---------------------------------------------------------------------------
# Test 10 — communication signals computed on a clean transcript
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_communication_signals_computed_on_clean_transcript(
    voice_adaptive_input,
):
    voice_session = MagicMock()
    voice_session.id = 1
    voice_session.status = "completed"

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=voice_session)
    mock_db.add = MagicMock()  # SQLAlchemy add() is synchronous

    # A 35-word transcript so the structure signal (>= 30 words) is engaged.
    transcript = " ".join(f"word{i}" for i in range(35))

    rubric_json = json.dumps(
        {
            "dimensions": [
                {"name": "thinking", "score": 0.8, "feedback": "Clear reasoning."},
                {"name": "soft", "score": 0.7, "feedback": "Well articulated."},
                {"name": "work", "score": 0.7, "feedback": "Concrete design."},
                {"name": "growth", "score": 0.6, "feedback": "Open to iteration."},
            ],
            "overall": 0.75,
        }
    )
    mock_response = MagicMock()
    mock_response.content = rubric_json
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    mock_card = MagicMock()
    mock_card.id = 5

    with (
        patch(f"{_EVAL}.async_session", return_value=_make_session_mock(mock_db)),
        patch(
            f"{_EVAL}.get_transcript_text",
            AsyncMock(return_value=(transcript, 0.80)),
        ),
        _patch_traced_llm(mock_llm),
        patch(f"{_EVAL}._write_grade_result", AsyncMock(return_value=1)),
        patch(
            f"{_EVAL}.run_memory_agent",
            AsyncMock(return_value=(mock_card, "summary")),
        ),
    ):
        result = await evaluate_voice_response(voice_adaptive_input)

    assert result.flagged is False
    assert result.average_confidence == 0.80
