"""Speech-to-text gateway — canonical entry for transcription calls.

Feature code must not call ``litellm.atranscription`` directly. Use
:func:`atranscribe_audio` so STT shares retry, Prometheus metrics, and
Langfuse session tags with the rest of the LLM gateway.
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass

import litellm
from tenacity import RetryCallState, retry, stop_after_attempt, wait_exponential

from app.config import Settings, get_settings
from app.core.llm import get_langfuse_client
from app.core.logging import get_logger
from app.core.metrics import record_llm_call
from app.core.tracing import LangfuseTraceContext, build_langfuse_metadata

_logger = get_logger(__name__)

_MAX_RETRIES = 3
_TOOL_NAME = "voice_stt"


@dataclass(frozen=True)
class TranscriptionResult:
    """Outcome of a single audio transcription request."""

    text: str
    confidence: float


def _log_retry(retry_state: RetryCallState) -> None:
    _logger.warning("stt_call_retrying", attempt_number=retry_state.attempt_number)


def _confidence_from_response(response: object) -> float:
    confidence = 1.0
    segments = getattr(response, "segments", None)
    if segments:
        avg_no_speech = sum(
            s.get("no_speech_prob", 0.0) for s in segments
        ) / len(segments)
        confidence = 1.0 - avg_no_speech
    return confidence


@retry(
    stop=stop_after_attempt(_MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    before_sleep=_log_retry,
    reraise=True,
)
async def _call_transcription_api(
    *,
    audio_bytes: bytes,
    settings: Settings,
    filename: str,
) -> object:
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = filename
    return await litellm.atranscription(
        model=settings.TRANSCRIPTION_MODEL,
        file=audio_file,
        api_base=settings.LITELLM_BASE_URL or None,
        api_key=settings.LITELLM_API_KEY.get_secret_value(),
    )


async def atranscribe_audio(
    audio_bytes: bytes,
    *,
    settings: Settings | None = None,
    trace: LangfuseTraceContext | None = None,
    filename: str = "audio.webm",
) -> TranscriptionResult:
    """Transcribe audio via LiteLLM with retry, metrics, and Langfuse tracing."""
    settings = settings or get_settings()
    model = settings.TRANSCRIPTION_MODEL
    metadata = build_langfuse_metadata(trace)
    langfuse = get_langfuse_client()
    start = time.perf_counter()
    status = "error"

    try:
        with langfuse.start_as_current_observation(
            name="voice_stt",
            as_type="generation",
            model=model,
            metadata=metadata or None,
        ) as observation:
            if trace and trace.session_id:
                observation.update_trace(session_id=trace.session_id)
            response = await _call_transcription_api(
                audio_bytes=audio_bytes,
                settings=settings,
                filename=filename,
            )
            text = getattr(response, "text", None) or ""
            confidence = _confidence_from_response(response)
            observation.update(output={"chars": len(text), "confidence": confidence})
            status = "success"
            return TranscriptionResult(text=text, confidence=confidence)
    except Exception as exc:  # noqa: BLE001 — callers expect empty transcript on failure
        _logger.error("stt_transcription_failed", error=str(exc))
        return TranscriptionResult(text="", confidence=0.0)
    finally:
        record_llm_call(model, _TOOL_NAME, status, time.perf_counter() - start)


__all__ = ["TranscriptionResult", "atranscribe_audio"]
