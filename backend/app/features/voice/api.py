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
    VoiceAdaptiveInput,
    VoiceAdaptivePublicResponse,
    VoiceSessionComplete,
    VoiceSessionCreate,
    VoiceSessionRead,
    VoiceSessionStart,
    VoiceSessionStartResponse,
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


@router.post("/adaptive/sessions", response_model=VoiceSessionStartResponse)
async def start_adaptive_voice_session(
    payload: VoiceSessionStart,
    db: AsyncSession = Depends(get_db),
) -> VoiceSessionStartResponse:
    """Create a new voice session for the adaptive loop.

    Call this to obtain a ``voice_session_id`` before opening the WebSocket
    recording stream.

    Args:
        payload: The adaptive session start request.
        db: Async database session dependency.

    Returns:
        The new session's id, question, time limit, and initial status.
    """
    from app.features.voice.models import VoiceSession

    new_session = VoiceSession(
        # FK deferred until assessment_sessions table exists
        session_id=payload.session_id,
        question_text=(
            payload.question_text
            if hasattr(VoiceSession, "question_text")
            else None
        ),
        question_index=(
            payload.question_index
            if hasattr(VoiceSession, "question_index")
            else None
        ),
        time_limit_seconds=payload.time_limit_seconds,
        status="pending",
    )
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)
    _logger.info("adaptive_session_created", voice_session_id=new_session.id)
    return VoiceSessionStartResponse(
        voice_session_id=new_session.id,
        session_id=payload.session_id,
        question_text=payload.question_text,
        question_index=payload.question_index,
        time_limit_seconds=payload.time_limit_seconds,
        status="pending",
    )


@router.post(
    "/adaptive/sessions/{voice_session_id}/process",
    response_model=VoiceAdaptivePublicResponse,
)
async def process_voice_session(
    voice_session_id: int,
    payload: VoiceAdaptiveInput,
) -> VoiceAdaptivePublicResponse:
    """Run the full adaptive loop for a completed voice session.

    Call this after the WebSocket sends ``session_complete``. Returns the next
    question embedded in ``adaptive_contract``. Grading is silent — the internal
    :class:`VoiceAdaptiveOutput` (scores, transcript, memory summary, flag
    reason) never crosses this boundary; only learner-facing navigation data is
    returned via :class:`VoiceAdaptivePublicResponse`.

    Args:
        voice_session_id: Primary key of the voice session to process.
        payload: The adaptive evaluation request.

    Returns:
        The public response with a sanitized ``adaptive_contract`` (next question
        text, difficulty, follow-up depth, stop) and no grading signals.

    Raises:
        HTTPException: 422 if ``voice_session_id`` in path does not match body.
    """
    from fastapi import HTTPException

    if payload.voice_session_id != voice_session_id:
        raise HTTPException(
            status_code=422,
            detail="voice_session_id mismatch between path and body",
        )
    from app.features.voice.loop import run_voice_adaptive_loop

    full_output = await run_voice_adaptive_loop(payload)

    # Strip every internal grading signal before crossing the API boundary.
    # AdaptiveContract.model_dump() carries focus_dimension, memory_summary,
    # session_id, tool_type, and cumulative_scores — none of which the learner
    # may see. Only the five navigation fields below are exposed.
    raw_contract = full_output.adaptive_contract
    safe_contract: dict | None = None
    if raw_contract:
        safe_contract = {
            "next_question_text": raw_contract.get("next_question_text"),
            "difficulty": raw_contract.get("difficulty"),
            "follow_up_depth": raw_contract.get("follow_up_depth"),
            "stop": raw_contract.get("stop", False),
            "question_index": raw_contract.get("question_index"),
        }

    return VoiceAdaptivePublicResponse(
        session_id=full_output.session_id,
        voice_session_id=full_output.voice_session_id,
        question_index=full_output.question_index,
        flagged=full_output.flagged,
        adaptive_contract=safe_contract,
    )


@router.get("/adaptive/sessions/{session_id}/analysis")
async def get_session_analysis(session_id: str) -> dict:
    """Return the current analysis state for a session.

    Exposes only mastery level and dimension focus — no raw scores are returned.

    Args:
        session_id: Owning assessment session identifier.

    Returns:
        A summary dict with total voice questions answered, mastery level,
        recommended focus dimension, and recommended probing depth.
    """
    from app.features.voice.analysis import analyze_voice_session

    analysis = await analyze_voice_session(session_id, current_question_index=0)
    return {
        "session_id": session_id,
        "total_voice_questions": analysis["total_cards"],
        "mastery_level": analysis["mastery_level"],
        "focus_dimension": analysis.get("weakest_dimension"),
        "recommended_depth": analysis.get("recommended_follow_up_depth"),
    }
