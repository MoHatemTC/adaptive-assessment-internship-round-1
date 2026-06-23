"""Unit tests for vision JSON completions."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.vision import VisionGradingUnavailable, acompletion_vision_json


@pytest.mark.asyncio
async def test_acompletion_vision_json_parses_kimi_fence():
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='```json\n{"score": 0.75, "feedback": "good"}\n```'))
    ]

    with patch("app.core.vision.litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_response
        with patch("app.core.vision.prefers_raw_json_model", return_value=True):
            result = await acompletion_vision_json([{"role": "user", "content": "x"}])

    assert result == {"score": 0.75, "feedback": "good"}
    call_kwargs = mock_llm.await_args.kwargs
    assert "response_format" not in call_kwargs


@pytest.mark.asyncio
async def test_acompletion_vision_json_uses_structured_output_for_gpt4o():
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"score": 1.0, "feedback": "perfect"}'))
    ]

    with patch("app.core.vision.litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_response
        with patch("app.core.vision.prefers_raw_json_model", return_value=False):
            result = await acompletion_vision_json([{"role": "user", "content": "x"}])

    assert result["score"] == 1.0
    assert mock_llm.await_args.kwargs["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_acompletion_vision_json_raises_on_provider_failure():
    with patch("app.core.vision.litellm.acompletion", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = RuntimeError("503 unavailable")
        with pytest.raises(VisionGradingUnavailable):
            await acompletion_vision_json([{"role": "user", "content": "x"}])
