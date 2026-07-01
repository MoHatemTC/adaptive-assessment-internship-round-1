"""End-to-end voice grading + G-Eval regression (opt-in)."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.evals.grading_goldens import VOICE_GRADING_GOLDENS
from app.features.voice.evaluation import _grade_transcript_with_llm

pytestmark = pytest.mark.deepeval

_RUN_DEEPEVAL = os.environ.get("RUN_DEEPEVAL", "").strip() == "1"
_SKIP_REASON = "Set RUN_DEEPEVAL=1 and configure LITELLM_API_KEY to run live grading G-Eval"


@pytest.mark.asyncio
@pytest.mark.skipif(not _RUN_DEEPEVAL, reason=_SKIP_REASON)
async def test_live_voice_grader_output_is_valid_json():
    """Grade a strong golden transcript with the production LLM gateway."""
    from app.core.llm import get_llm_with_tracing

    golden = next(g for g in VOICE_GRADING_GOLDENS if g.quality_band == "strong")
    llm, _callbacks = get_llm_with_tracing()
    rubric = await _grade_transcript_with_llm(
        golden.question,
        golden.transcript,
        golden.difficulty,
        llm,
        invoke_config={},
    )
    payload = json.loads(json.dumps(rubric.model_dump()))
    assert 0.0 <= payload["overall"] <= 1.0
    assert len(payload["dimensions"]) >= 4


@pytest.mark.asyncio
async def test_offline_voice_grader_mock_serializes_rubric():
    """Sanity: mocked grader output is JSON-safe for the G-Eval harness (no API)."""
    golden = VOICE_GRADING_GOLDENS[0]
    mock_response = MagicMock()
    mock_response.content = golden.rubric_json
    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    rubric = await _grade_transcript_with_llm(
        golden.question,
        golden.transcript,
        golden.difficulty,
        mock_llm,
    )
    assert rubric.overall > 0.5
