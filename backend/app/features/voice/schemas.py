"""Pydantic v2 request/response schemas for the voice interview feature.

These schemas define the API contract for the voice endpoints: creating a
session, reading its state, reporting per-chunk transcript deltas, and
signalling completion. :class:`VoiceSessionRead` enables
``from_attributes`` so it can be built directly from a
:class:`~app.features.voice.models.VoiceSession` ORM row.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.shared.schemas.memory import DifficultyLevel


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


#: Reason a voice transcript was excluded from grading. Checked in priority
#: order: lifecycle status first (``timed_out``/``failed``), then content
#: quality (``empty_transcript``/``low_confidence``).
TranscriptFlag = Literal[
    "empty_transcript",  # fewer than 10 non-whitespace chars
    "low_confidence",  # average STT confidence below 0.65
    "timed_out",  # voice_session.status == "timed_out"
    "failed",  # voice_session.status == "failed"
]


class VoiceSessionStart(BaseModel):
    """Request to start an adaptive, time-boxed voice interview.

    Attributes:
        session_id: Owning assessment session identifier.
        question_text: The interview question to pose.
        question_index: Zero-based position in the assessment blueprint.
        time_limit_seconds: Maximum interview duration in seconds (30–300).
        target_difficulty: Difficulty tier selected by the adaptive layer.
        learner_profile: Opaque learner context (name, role, level, ...).
        admin_config: Opaque admin constraints (max difficulty, topics, ...).
    """

    session_id: str
    question_text: str
    question_index: int = Field(ge=0)
    time_limit_seconds: int = Field(ge=30, le=300)
    target_difficulty: DifficultyLevel
    learner_profile: dict
    admin_config: dict


class VoiceSessionStartResponse(BaseModel):
    """Acknowledgement returned after an adaptive voice session is created.

    Attributes:
        voice_session_id: Surrogate primary key of the new voice session.
        session_id: Owning assessment session identifier.
        question_text: The interview question posed.
        question_index: Zero-based position in the assessment blueprint.
        time_limit_seconds: Maximum interview duration in seconds.
        status: Lifecycle state of the freshly created session.
    """

    voice_session_id: int
    session_id: str
    question_text: str
    question_index: int
    time_limit_seconds: int
    status: str


class VoiceAdaptiveInput(BaseModel):
    """Input to the silent evaluation layer (Layers 5+6) for one response.

    Attributes:
        session_id: Owning assessment session identifier.
        voice_session_id: Surrogate primary key of the voice session.
        question_index: Zero-based position in the assessment blueprint.
        question_text: The interview question that was posed.
        target_difficulty: Difficulty tier the question targeted.
        learner_profile: Opaque learner context.
        admin_config: Opaque admin constraints.
        follow_up_depth: How aggressively the adaptive layer should probe next.
    """

    session_id: str
    voice_session_id: int
    question_index: int = Field(ge=0)
    question_text: str
    target_difficulty: DifficultyLevel
    learner_profile: dict
    admin_config: dict
    follow_up_depth: Literal["simple", "deep"] = "simple"


class VoiceAdaptiveOutput(BaseModel):
    """Silent output of the evaluation layer. Never shown to the learner.

    Attributes:
        session_id: Owning assessment session identifier.
        voice_session_id: Surrogate primary key of the voice session.
        question_index: Zero-based position in the assessment blueprint.
        transcript: The assembled transcript text (empty if none / flagged).
        average_confidence: Mean STT confidence across transcript chunks.
        flagged: Whether the transcript was excluded from grading.
        flag_reason: Why the transcript was flagged, or ``None`` if clean.
        grade_result_id: PK of the persisted ``grade_results`` row, if written.
        memory_card_id: PK of the persisted ``memory_cards`` row, if written.
        memory_summary: Narrative progress summary from the memory agent.
        adaptive_contract: Optional next-question contract (unset here).
    """

    session_id: str
    voice_session_id: int
    question_index: int
    transcript: str
    average_confidence: float
    flagged: bool
    flag_reason: Optional[TranscriptFlag] = None
    grade_result_id: Optional[int] = None
    memory_card_id: Optional[int] = None
    memory_summary: str = ""
    adaptive_contract: Optional[dict] = None
