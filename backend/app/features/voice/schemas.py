"""Pydantic v2 request/response schemas for the voice interview feature.

These schemas define the API contract for the voice endpoints: creating a
session, reading its state, reporting per-chunk transcript deltas, and
signalling completion. :class:`VoiceSessionRead` enables
``from_attributes`` so it can be built directly from a
:class:`~app.features.voice.models.VoiceSession` ORM row.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VoiceSessionCreate(BaseModel):
    """Request body for creating a new voice interview session.

    Attributes:
        session_id: Owning assessment session identifier.
        time_limit_seconds: Maximum interview duration in seconds.
    """

    session_id: str
    time_limit_seconds: int

    model_config = ConfigDict(from_attributes=True)


class VoiceSessionRead(BaseModel):
    """Serialized view of a voice session returned to API clients.

    Built directly from the ORM row via ``from_attributes``.

    Attributes:
        id: Surrogate primary key of the session.
        session_id: Owning assessment session identifier.
        status: Lifecycle state (``"pending"``, ``"active"``, ``"completed"``).
        time_limit_seconds: Maximum interview duration in seconds.
        started_at: Timestamp the interview became active, or ``None``.
        ended_at: Timestamp the interview finished, or ``None`` while running.
        created_at: Server-set timestamp of row insertion.
    """

    id: int
    session_id: str
    status: str
    time_limit_seconds: int
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VoiceTranscriptChunk(BaseModel):
    """A single real-time transcript delta for one session.

    Attributes:
        voice_session_id: Identifier of the owning voice session.
        chunk_index: Zero-based ordering index of the chunk within the session.
        transcript_text: The recognized text for this chunk.
        is_final: Whether this chunk is finalized (``True``) or interim
            (``False``).
    """

    voice_session_id: int
    chunk_index: int
    transcript_text: str
    is_final: bool

    model_config = ConfigDict(from_attributes=True)


class VoiceSessionComplete(BaseModel):
    """Result returned when a voice session is finalized.

    Attributes:
        session_id: Owning assessment session identifier.
        final_transcript: The full assembled transcript text.
        duration_seconds: Total elapsed interview duration in seconds.
    """

    session_id: str
    final_transcript: str
    duration_seconds: int

    model_config = ConfigDict(from_attributes=True)


class VoiceSessionStatus(BaseModel):
    """Lightweight live status of a voice session.

    Attributes:
        session_id: Owning assessment session identifier.
        status: Lifecycle state (``"pending"``, ``"active"``, ``"completed"``).
        elapsed_seconds: Seconds elapsed since the interview started.
    """

    session_id: str
    status: str
    elapsed_seconds: int

    model_config = ConfigDict(from_attributes=True)
