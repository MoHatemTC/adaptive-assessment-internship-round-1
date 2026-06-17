"""Voice interview persistence and LiteLLM speech-to-text integration.

This layer owns the voice session lifecycle (create -> start -> end), per-chunk
transcript persistence, and the real-time transcription call via LiteLLM. It
mirrors the MCQ feature's service conventions: SQLModel ``select`` queries via
``db.exec``, ``db.flush`` (commit is owned by the caller / ``get_db``), a 404
helper for missing sessions, and structured ``structlog`` events.

The raw transcript is persisted in full so the silent LLM judge can score it
later; scores are never surfaced to the learner.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings, get_settings
from app.core.database import async_session
from app.core.logging import get_logger
from app.features.voice.models import VoiceSession, VoiceTranscript
from app.features.voice.schemas import VoiceTranscriptChunk

_logger = get_logger(__name__)

#: Minimum transcription confidence for a chunk to count toward the final
#: transcript. Chunks below this are still stored (for audit/debugging) but
#: marked ``is_final=False`` so :func:`end_voice_session` excludes them.
CONFIDENCE_THRESHOLD: float = 0.6


async def _get_voice_session_or_404(
    db: AsyncSession,
    voice_session_id: int,
) -> VoiceSession:
    """Fetch a voice session by id or raise a 404.

    Args:
        db: Active async database session.
        voice_session_id: Primary key of the voice session to fetch.

    Returns:
        The matching :class:`~app.features.voice.models.VoiceSession`.

    Raises:
        HTTPException: 404 if no session matches ``voice_session_id``.
    """
    result = await db.exec(
        select(VoiceSession).where(VoiceSession.id == voice_session_id)
    )
    voice_session = result.first()

    if voice_session is None:
        _logger.warning(
            "voice_session_not_found", voice_session_id=voice_session_id
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice session not found",
        )

    return voice_session


async def _transcribe_chunk(
    audio_chunk: bytes,
    settings: Settings,
    logger: Any,
) -> tuple[str, float]:
    """Transcribe a single audio chunk via LiteLLM and return text + confidence.

    Isolates the LiteLLM transcription call so callers (and tests) can treat
    transcription as a single seam.

    Args:
        audio_chunk: Raw audio payload for one streamed chunk.
        settings: Application settings, used to resolve the STT model and the
            LiteLLM proxy base URL.
        logger: Structured logger used to record the outcome.

    Returns:
        A ``(transcript_text, confidence)`` tuple. ``transcript_text`` is an
        empty string and ``confidence`` is ``0.0`` if transcription fails.
    """
    import io

    import litellm

    audio_file = io.BytesIO(audio_chunk)
    audio_file.name = "audio.webm"

    try:
        response = await litellm.atranscription(
            model=settings.STT_MODEL,
            file=audio_file,
            api_base=settings.LITELLM_BASE_URL,
            api_key=settings.LITELLM_API_KEY.get_secret_value(),
        )
        transcript_text = response.text or ""

        confidence = 1.0
        if hasattr(response, "segments") and response.segments:
            avg_no_speech = sum(
                s.get("no_speech_prob", 0.0) for s in response.segments
            ) / len(response.segments)
            confidence = 1.0 - avg_no_speech

        logger.info(
            "whisper_transcription_ok",
            chars=len(transcript_text),
            confidence=confidence,
        )
        return transcript_text, confidence

    except Exception as e:
        logger.error("whisper_transcription_failed", error=str(e))
        return "", 0.0


async def create_voice_session(
    db: AsyncSession,
    session_id: str,
    time_limit: int,
) -> VoiceSession:
    """Create a new voice interview session in ``pending`` status.

    Args:
        db: Active async database session.
        session_id: Owning assessment session identifier.
        time_limit: Maximum interview duration in seconds.

    Returns:
        The newly created :class:`~app.features.voice.models.VoiceSession`.
    """
    voice_session = VoiceSession(
        session_id=session_id,
        time_limit_seconds=time_limit,
    )
    db.add(voice_session)
    await db.flush()
    # Load server-default columns (status, created_at) so callers can serialize
    # the row without triggering an async lazy-load on unset attributes.
    await db.refresh(voice_session)

    _logger.info(
        "voice_session_created",
        voice_session_id=voice_session.id,
        session_id=session_id,
        time_limit_seconds=time_limit,
    )

    return voice_session


async def start_voice_session(
    db: AsyncSession,
    voice_session_id: int,
) -> VoiceSession:
    """Mark a voice session as ``active`` and stamp its start time.

    Args:
        db: Active async database session.
        voice_session_id: Primary key of the voice session to start.

    Returns:
        The updated :class:`~app.features.voice.models.VoiceSession`.

    Raises:
        HTTPException: 404 if the voice session does not exist.
    """
    voice_session = await _get_voice_session_or_404(db, voice_session_id)

    voice_session.status = "active"
    voice_session.started_at = datetime.now(timezone.utc)
    db.add(voice_session)
    await db.flush()

    _logger.info(
        "voice_session_started",
        voice_session_id=voice_session_id,
        started_at=voice_session.started_at.isoformat(),
    )

    return voice_session


async def stream_audio_chunk(
    voice_session_id: int,
    audio_bytes: bytes,
) -> VoiceTranscriptChunk:
    """Transcribe an audio chunk, persist it, and return the transcript delta.

    Runs outside the FastAPI request lifecycle (driven by the WebSocket loop),
    so it opens its own database session via
    :data:`~app.core.database.async_session`. The chunk's ordering index is
    derived from the count of chunks already stored for the session.

    Args:
        voice_session_id: Primary key of the owning voice session.
        audio_bytes: Raw audio payload for this chunk.

    Returns:
        A :class:`~app.features.voice.schemas.VoiceTranscriptChunk` describing
        the persisted transcript delta.
    """
    transcript_text, confidence = await _transcribe_chunk(
        audio_bytes, get_settings(), _logger
    )

    async with async_session() as db:
        count_result = await db.exec(
            select(func.count())
            .select_from(VoiceTranscript)
            .where(VoiceTranscript.voice_session_id == voice_session_id)
        )
        chunk_index = int(count_result.one())

        # Gate chunks by confidence: a missing score or one at/above the
        # threshold is treated as final; a low score is stored but excluded
        # from the assembled transcript by marking it non-final.
        if confidence is None or confidence >= CONFIDENCE_THRESHOLD:
            is_final = True
        else:
            is_final = False
            _logger.warning(
                "low_confidence_transcript",
                chunk_index=chunk_index,
                confidence=confidence,
            )

        transcript = VoiceTranscript(
            voice_session_id=voice_session_id,
            chunk_index=chunk_index,
            transcript_text=transcript_text,
            speaker_confidence=confidence,
            is_final=is_final,
        )
        db.add(transcript)
        await db.commit()
        await db.refresh(transcript)

    _logger.info(
        "voice_chunk_transcribed",
        voice_session_id=voice_session_id,
        chunk_index=chunk_index,
        is_final=is_final,
    )

    return VoiceTranscriptChunk.model_validate(transcript)


async def end_voice_session(
    db: AsyncSession,
    voice_session_id: int,
) -> str:
    """Mark a voice session ``completed`` and assemble its final transcript.

    The final transcript is built from the session's finalized chunks in order;
    if none are marked final, all chunks are used as a fallback.

    Args:
        db: Active async database session.
        voice_session_id: Primary key of the voice session to end.

    Returns:
        The assembled final transcript text (empty string if no chunks exist).

    Raises:
        HTTPException: 404 if the voice session does not exist.
    """
    voice_session = await _get_voice_session_or_404(db, voice_session_id)

    voice_session.status = "completed"
    voice_session.ended_at = datetime.now(timezone.utc)
    db.add(voice_session)

    chunks = await get_transcript(db, voice_session_id)
    final_parts = [c.transcript_text for c in chunks if c.is_final]
    if not final_parts:
        final_parts = [c.transcript_text for c in chunks]
    final_transcript = " ".join(
        part.strip() for part in final_parts if part.strip()
    )

    await db.flush()

    _logger.info(
        "voice_session_ended",
        voice_session_id=voice_session_id,
        chunk_count=len(chunks),
        transcript_length=len(final_transcript),
    )

    return final_transcript


async def get_voice_session(
    db: AsyncSession,
    voice_session_id: int,
) -> VoiceSession:
    """Return a voice session by id.

    Args:
        db: Active async database session.
        voice_session_id: Primary key of the voice session to fetch.

    Returns:
        The matching :class:`~app.features.voice.models.VoiceSession`.

    Raises:
        HTTPException: 404 if the voice session does not exist.
    """
    return await _get_voice_session_or_404(db, voice_session_id)


async def get_transcript(
    db: AsyncSession,
    voice_session_id: int,
) -> list[VoiceTranscript]:
    """Return all transcript chunks for a session, ordered by chunk index.

    Args:
        db: Active async database session.
        voice_session_id: Primary key of the owning voice session.

    Returns:
        The session's :class:`~app.features.voice.models.VoiceTranscript` rows
        in ascending ``chunk_index`` order (empty list if none exist).
    """
    result = await db.exec(
        select(VoiceTranscript)
        .where(VoiceTranscript.voice_session_id == voice_session_id)
        .order_by(VoiceTranscript.chunk_index)
    )
    return list(result.all())
