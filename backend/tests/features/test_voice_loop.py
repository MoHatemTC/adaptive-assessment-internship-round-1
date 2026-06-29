"""Tests for the voice adaptive loop orchestrator and its API endpoints.

Layer functions and DB access are mocked so the suite runs without a live
database or API key, following the patterns in test_voice_evaluation.py.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.features.voice.loop import run_voice_adaptive_loop
from app.features.voice.schemas import VoiceAdaptiveInput, VoiceAdaptiveOutput
from app.shared.schemas.memory import AdaptiveContract

_LOOP = "app.features.voice.loop"


@pytest.fixture
def loop_input() -> VoiceAdaptiveInput:
    """Minimal valid adaptive loop input for one voice response."""
    return VoiceAdaptiveInput(
        session_id="loop-session-uuid",
        voice_session_id=1,
        question_index=0,
        question_text="Describe your debugging process for a production outage.",
        target_difficulty="intermediate",
        learner_profile={"role": "backend_developer", "level": "senior"},
        admin_config={"max_difficulty": "advanced"},
    )


def _make_eval_output(**overrides) -> VoiceAdaptiveOutput:
    """Return a minimal VoiceAdaptiveOutput, optionally overridden."""
    defaults = dict(
        session_id="loop-session-uuid",
        voice_session_id=1,
        question_index=0,
        transcript="I'd start by checking the error logs.",
        average_confidence=0.88,
        flagged=False,
        memory_summary="Strong incident response knowledge demonstrated.",
    )
    defaults.update(overrides)
    return VoiceAdaptiveOutput(**defaults)


def _make_contract(**overrides) -> AdaptiveContract:
    """Return a minimal AdaptiveContract, optionally overridden."""
    defaults = dict(
        session_id="loop-session-uuid",
        question_index=1,
        tool_type="voice",
        difficulty="advanced",
        stop=False,
        memory_summary="Strong incident response knowledge demonstrated.",
    )
    defaults.update(overrides)
    return AdaptiveContract(**defaults)


def _make_analysis() -> dict:
    """Return a minimal analysis dict."""
    return {
        "session_id": "loop-session-uuid",
        "total_cards": 1,
        "dimensions": {
            "thinking": {"signal_count": 1, "total": 1, "rate": 1.0},
            "soft": {"signal_count": 0, "total": 1, "rate": 0.0},
            "work": {"signal_count": 1, "total": 1, "rate": 1.0},
            "digital_ai": {"signal_count": 0, "total": 1, "rate": 0.0},
            "growth": {"signal_count": 1, "total": 1, "rate": 1.0},
        },
        "weakest_dimension": "soft",
        "strongest_dimension": "thinking",
        "mastery_level": "high",
        "recommended_follow_up_depth": "deep",
    }


# ---------------------------------------------------------------------------
# Test 1 — loop returns a VoiceAdaptiveOutput with contract populated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_loop_returns_adaptive_output(loop_input):
    eval_out = _make_eval_output()
    contract = _make_contract()

    with (
        patch(f"{_LOOP}.evaluate_voice_response", AsyncMock(return_value=eval_out)),
        patch(
            f"{_LOOP}.analyze_voice_session",
            AsyncMock(return_value=_make_analysis()),
        ),
        patch(
            f"{_LOOP}.generate_next_voice_question",
            AsyncMock(return_value=("Next question?", "advanced", "deep")),
        ),
        patch(
            f"{_LOOP}.build_voice_adaptive_contract", AsyncMock(return_value=contract)
        ),
    ):
        result = await run_voice_adaptive_loop(loop_input)

    assert isinstance(result, VoiceAdaptiveOutput)
    assert result.adaptive_contract is not None


# ---------------------------------------------------------------------------
# Test 2 — next_question_text and follow_up_depth appear in contract dict
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_loop_next_question_in_contract(loop_input):
    eval_out = _make_eval_output()
    contract = _make_contract()
    next_q = "Walk me through your incident response playbook."

    with (
        patch(f"{_LOOP}.evaluate_voice_response", AsyncMock(return_value=eval_out)),
        patch(
            f"{_LOOP}.analyze_voice_session",
            AsyncMock(return_value=_make_analysis()),
        ),
        patch(
            f"{_LOOP}.generate_next_voice_question",
            AsyncMock(return_value=(next_q, "advanced", "deep")),
        ),
        patch(
            f"{_LOOP}.build_voice_adaptive_contract", AsyncMock(return_value=contract)
        ),
    ):
        result = await run_voice_adaptive_loop(loop_input)

    assert result.adaptive_contract["next_question_text"] == next_q
    assert result.adaptive_contract["follow_up_depth"] == "deep"


# ---------------------------------------------------------------------------
# Test 3 — flagged output propagates through the loop unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_loop_propagates_flagged_output(loop_input):
    flagged_out = _make_eval_output(
        flagged=True, flag_reason="timed_out", transcript="", average_confidence=0.0
    )
    contract = _make_contract()

    with (
        patch(
            f"{_LOOP}.evaluate_voice_response", AsyncMock(return_value=flagged_out)
        ),
        patch(
            f"{_LOOP}.analyze_voice_session",
            AsyncMock(return_value=_make_analysis()),
        ),
        patch(
            f"{_LOOP}.generate_next_voice_question",
            AsyncMock(return_value=("Fallback question.", "beginner", "simple")),
        ),
        patch(
            f"{_LOOP}.build_voice_adaptive_contract", AsyncMock(return_value=contract)
        ),
    ):
        result = await run_voice_adaptive_loop(loop_input)

    assert result.flagged is True
    assert result.flag_reason == "timed_out"


# ---------------------------------------------------------------------------
# Test 4 — layers are called in order: evaluate → analyse → generate → build
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_loop_calls_layers_in_order(loop_input):
    call_order: list[str] = []
    eval_out = _make_eval_output()
    contract = _make_contract()

    async def _eval(inp):
        call_order.append("evaluate")
        return eval_out

    async def _analyse(sid, idx):
        call_order.append("analyse")
        return _make_analysis()

    async def _generate(**kwargs):
        call_order.append("generate")
        return ("Next question?", "advanced", "deep")

    async def _build(**kwargs):
        call_order.append("build")
        return contract

    with (
        patch(f"{_LOOP}.evaluate_voice_response", _eval),
        patch(f"{_LOOP}.analyze_voice_session", _analyse),
        patch(f"{_LOOP}.generate_next_voice_question", _generate),
        patch(f"{_LOOP}.build_voice_adaptive_contract", _build),
    ):
        await run_voice_adaptive_loop(loop_input)

    assert call_order == ["evaluate", "analyse", "generate", "build"]


# ---------------------------------------------------------------------------
# Helpers shared by endpoint tests
# ---------------------------------------------------------------------------

def _build_test_app() -> FastAPI:
    """Return a fresh FastAPI app with the voice router mounted."""
    from app.core.deps import get_db
    from app.features.voice.api import router as voice_router

    app = FastAPI()
    app.include_router(voice_router)

    async def _mock_get_db():
        db = AsyncMock()

        async def _refresh(obj):
            obj.id = 42

        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock(side_effect=_refresh)
        yield db

    app.dependency_overrides[get_db] = _mock_get_db
    return app


# ---------------------------------------------------------------------------
# Test 5 — POST /voice/adaptive/sessions returns 200 with voice_session_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_adaptive_session_endpoint_201():
    app = _build_test_app()

    # Proctoring readiness is enforced separately; isolate the start-endpoint
    # contract here with a mocked, fully-async test DB.
    with patch(
        "app.proctoring.enforcement.ensure_tool_session_allowed",
        new=AsyncMock(return_value=None),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/voice/adaptive/sessions",
                json={
                    "session_id": "adaptive-session-1",
                    "question_text": "Tell me about a recent project.",
                    "question_index": 0,
                    "time_limit_seconds": 60,
                    "target_difficulty": "intermediate",
                    "learner_profile": {},
                    "admin_config": {},
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert "voice_session_id" in body
    assert body["status"] == "pending"


# ---------------------------------------------------------------------------
# Test 6 — mismatched voice_session_id in path vs body returns 422
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_endpoint_rejects_mismatched_id():
    app = _build_test_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/voice/adaptive/sessions/999/process",
            json={
                "session_id": "loop-session-uuid",
                "voice_session_id": 1,
                "question_index": 0,
                "question_text": "Describe your debugging process.",
                "target_difficulty": "intermediate",
                "learner_profile": {"role": "backend_developer", "level": "senior"},
                "admin_config": {"max_difficulty": "advanced"},
                "follow_up_depth": "simple",
            },
        )

    assert response.status_code == 422
