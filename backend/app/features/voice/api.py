"""FastAPI routes for the voice interview feature.

Exposes the voice session lifecycle: create a session, stream audio over a
WebSocket for real-time transcription, read the stored transcript, and end the
session with its assembled final transcript. The router is named ``router`` so
the application factory's auto-discovery registers it (with no extra prefix, so
``prefix="/voice"`` is the full path).

The streaming endpoint accepts binary audio frames, transcribes each via
Azure Whisper through the LiteLLM proxy, persists it, and echoes a
``transcript_delta`` message back to the client. The interview ends on client
disconnect or when the session's time limit elapses, at which point the final
transcript is assembled and saved.
"""

import asyncio
from typing import Dict, List

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import async_session
from app.core.deps import get_db
from app.core.logging import get_logger
from app.features.voice.schemas import (
    VoiceSessionComplete,
    VoiceSessionCreate,
    VoiceSessionRead,
    VoiceTranscriptChunk,
)
from app.features.voice.service import (
    create_voice_session,
    end_voice_session,
    get_transcript,
    get_voice_session,
    start_voice_session,
    stream_audio_chunk,
)

_logger = get_logger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


@router.get("/health")
def voice_health_check() -> Dict[str, str]:
    """Report that the voice feature is ready.

    Returns:
        A small status payload identifying the feature.
    """
    return {
        "status": "ready",
        "feature": "voice",
    }


@router.post("/sessions", response_model=VoiceSessionRead)
async def create_voice_interview(
    payload: VoiceSessionCreate,
    db: AsyncSession = Depends(get_db),
) -> VoiceSessionRead:
    """Create a new voice interview session in ``pending`` status.

    Args:
        payload: The owning assessment ``session_id`` and ``time_limit_seconds``.
        db: Async database session dependency.

    Returns:
        The newly created session serialized as :class:`VoiceSessionRead`.
    """
    voice_session = await create_voice_session(
        db=db,
        session_id=payload.session_id,
        time_limit=payload.time_limit_seconds,
    )
    return VoiceSessionRead.model_validate(voice_session)


@router.websocket("/sessions/{voice_session_id}/stream")
async def stream_voice_audio(
    websocket: WebSocket,
    voice_session_id: int,
) -> None:
    """Stream binary audio for real-time transcription over a WebSocket.

    On connect the session is marked active. Each received binary frame is
    transcribed and persisted, and a ``transcript_delta`` JSON message is sent
    back. The loop ends when the client disconnects or the session's time limit
    elapses, after which the final transcript is assembled, saved, and (when the
    socket is still open) sent as a ``session_complete`` message.

    Message sent to client per chunk::

        {"type": "transcript_delta", "text": "...", "is_final": bool}

    Args:
        websocket: The accepted client WebSocket connection.
        voice_session_id: Primary key of the voice session being streamed.

    Returns:
        None.
    """
    await websocket.accept()

    # Start the session and read its time limit for the streaming deadline.
    try:
        async with async_session() as db:
            voice_session = await start_voice_session(db, voice_session_id)
            time_limit = voice_session.time_limit_seconds
            await db.commit()
    except HTTPException:
        _logger.warning(
            "voice_stream_session_not_found", voice_session_id=voice_session_id
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    loop = asyncio.get_event_loop()
    deadline = loop.time() + time_limit

    _logger.info(
        "voice_stream_connected",
        voice_session_id=voice_session_id,
        time_limit_seconds=time_limit,
    )

    try:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                _logger.info(
                    "voice_stream_time_limit_reached",
                    voice_session_id=voice_session_id,
                )
                break

            try:
                audio_bytes = await asyncio.wait_for(
                    websocket.receive_bytes(), timeout=remaining
                )
            except asyncio.TimeoutError:
                _logger.info(
                    "voice_stream_time_limit_reached",
                    voice_session_id=voice_session_id,
                )
                break

            chunk = await stream_audio_chunk(voice_session_id, audio_bytes)
            await websocket.send_json(
                {
                    "type": "transcript_delta",
                    "text": chunk.transcript_text,
                    "is_final": chunk.is_final,
                }
            )
    except WebSocketDisconnect:
        _logger.info(
            "voice_stream_disconnected", voice_session_id=voice_session_id
        )

    # Finalize the session regardless of how the stream ended.
    async with async_session() as db:
        final_transcript = await end_voice_session(db, voice_session_id)
        await db.commit()

    try:
        await websocket.send_json(
            {"type": "session_complete", "final_transcript": final_transcript}
        )
        await websocket.close()
    except (WebSocketDisconnect, RuntimeError):
        # Client already gone; nothing more to send.
        pass


@router.get(
    "/sessions/{voice_session_id}/transcript",
    response_model=List[VoiceTranscriptChunk],
)
async def get_voice_transcript(
    voice_session_id: int,
    db: AsyncSession = Depends(get_db),
) -> List[VoiceTranscriptChunk]:
    """Return all stored transcript chunks for a session, in order.

    Args:
        voice_session_id: Primary key of the owning voice session.
        db: Async database session dependency.

    Returns:
        The session's transcript chunks as :class:`VoiceTranscriptChunk` items.
    """
    chunks = await get_transcript(db=db, voice_session_id=voice_session_id)
    return [VoiceTranscriptChunk.model_validate(chunk) for chunk in chunks]


@router.post(
    "/sessions/{voice_session_id}/end",
    response_model=VoiceSessionComplete,
)
async def end_voice_interview(
    voice_session_id: int,
    db: AsyncSession = Depends(get_db),
) -> VoiceSessionComplete:
    """End a voice session and return its assembled final transcript.

    Args:
        voice_session_id: Primary key of the voice session to end.
        db: Async database session dependency.

    Returns:
        The completion payload: owning ``session_id``, the final transcript, and
        total ``duration_seconds``.

    Raises:
        HTTPException: 404 if the voice session does not exist.
    """
    final_transcript = await end_voice_session(db, voice_session_id)
    voice_session = await get_voice_session(db, voice_session_id)

    duration_seconds = 0
    if voice_session.started_at is not None and voice_session.ended_at is not None:
        duration_seconds = int(
            (voice_session.ended_at - voice_session.started_at).total_seconds()
        )

    return VoiceSessionComplete(
        session_id=voice_session.session_id,
        final_transcript=final_transcript,
        duration_seconds=duration_seconds,
    )
