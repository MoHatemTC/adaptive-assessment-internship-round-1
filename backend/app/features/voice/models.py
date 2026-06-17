"""SQLAlchemy 2.0 ORM models for the voice interview feature.

These models use the SQLAlchemy 2.0 declarative style (``Mapped[...]`` +
``mapped_column()``) on the kernel's :class:`~app.core.database.Base`, mirroring
the MCQ reference feature. A :class:`VoiceSession` is a single time-boxed voice
interview; each :class:`VoiceTranscript` row is one real-time speech-to-text
chunk produced while that session is active. The assembled final transcript is
later fed to the silent LLM judge, so transcript content is persisted in full
and never trimmed for the learner's benefit.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func

from app.core.database import Base, Mapped, mapped_column


class VoiceSession(Base):
    """A single time-boxed voice interview session.

    A session is created in ``pending`` status, moves to ``active`` when audio
    streaming begins, and ends as ``completed`` when the time limit is reached
    or the learner stops manually. ``started_at`` / ``ended_at`` bound the live
    window; ``created_at`` records when the row was first inserted.

    Attributes:
        id: Surrogate primary key.
        session_id: Owning assessment session identifier. Stored as a plain
            indexed string for now (no FK until the sessions feature merges).
        status: Lifecycle state, one of ``"pending"``, ``"active"``, or
            ``"completed"``. Defaults to ``"pending"`` server-side.
        time_limit_seconds: Maximum interview duration in seconds.
        question_text: The interview question posed for this session, or ``None``
            for legacy rows created before adaptive columns existed.
        question_index: Zero-based position of the question in the assessment
            blueprint, or ``None`` for legacy rows.
        started_at: Timestamp the interview became active, or ``None`` if it has
            not started yet.
        ended_at: Timestamp the interview finished, or ``None`` while running.
        created_at: Server-set timestamp of row insertion.
    """

    __tablename__ = "voice_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # links to assessment session — no FK until sessions feature merges
    session_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )
    time_limit_seconds: Mapped[int] = mapped_column(nullable=False)
    # Adaptive loop context — nullable so pre-existing rows are preserved.
    question_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_index: Mapped[int | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VoiceTranscript(Base):
    """A single real-time transcript chunk belonging to a :class:`VoiceSession`.

    Chunks arrive in order as Azure Whisper (via the LiteLLM proxy) streams
    interim and final results. ``chunk_index`` preserves ordering, ``is_final``
    distinguishes settled text from interim hypotheses, and
    ``speaker_confidence`` carries the transcription confidence score when
    available.

    Attributes:
        id: Surrogate primary key.
        voice_session_id: Foreign key to the owning :class:`VoiceSession`.
        chunk_index: Zero-based ordering index of the chunk within the session.
        transcript_text: The recognized text for this chunk.
        speaker_confidence: Transcription confidence score in ``[0.0, 1.0]``,
            or ``None`` when not reported.
        is_final: Whether this chunk is a finalized transcript (``True``) or an
            interim hypothesis (``False``). Defaults to ``False`` server-side.
        created_at: Server-set timestamp of row insertion.
    """

    __tablename__ = "voice_transcripts"

    id: Mapped[int] = mapped_column(primary_key=True)
    voice_session_id: Mapped[int] = mapped_column(
        ForeignKey("voice_sessions.id"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    transcript_text: Mapped[str] = mapped_column(Text, nullable=False)
    speaker_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_final: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
