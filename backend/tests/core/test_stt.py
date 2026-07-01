"""Tests for the core speech-to-text gateway."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.stt import TranscriptionResult, atranscribe_audio
from app.core.tracing import LangfuseTraceContext


@pytest.mark.asyncio
async def test_atranscribe_audio_returns_text_and_confidence():
    mock_response = MagicMock()
    mock_response.text = "hello world"
    mock_response.segments = [{"no_speech_prob": 0.1}]

    mock_observation = MagicMock()
    mock_observation.__enter__ = MagicMock(return_value=mock_observation)
    mock_observation.__exit__ = MagicMock(return_value=False)
    mock_langfuse = MagicMock()
    mock_langfuse.start_as_current_observation.return_value = mock_observation

    with (
        patch("app.core.stt._call_transcription_api", new_callable=AsyncMock) as mock_api,
        patch("app.core.stt.get_langfuse_client", return_value=mock_langfuse),
        patch("app.core.stt.record_llm_call") as mock_metrics,
    ):
        mock_api.return_value = mock_response
        result = await atranscribe_audio(
            b"audio-bytes",
            trace=LangfuseTraceContext(
                session_id="sess-1",
                operation="voice_stt",
                tool="voice",
            ),
        )

    assert result == TranscriptionResult(text="hello world", confidence=0.9)
    mock_metrics.assert_called_once()
    mock_langfuse.start_as_current_observation.assert_called_once()
    mock_observation.update_trace.assert_called_once_with(session_id="sess-1")


@pytest.mark.asyncio
async def test_atranscribe_audio_returns_empty_on_failure():
    mock_observation = MagicMock()
    mock_observation.__enter__ = MagicMock(return_value=mock_observation)
    mock_observation.__exit__ = MagicMock(return_value=False)
    mock_langfuse = MagicMock()
    mock_langfuse.start_as_current_observation.return_value = mock_observation

    with (
        patch(
            "app.core.stt._call_transcription_api",
            new_callable=AsyncMock,
            side_effect=RuntimeError("provider down"),
        ),
        patch("app.core.stt.get_langfuse_client", return_value=mock_langfuse),
        patch("app.core.stt.record_llm_call"),
    ):
        result = await atranscribe_audio(b"audio-bytes")

    assert result.text == ""
    assert result.confidence == 0.0
