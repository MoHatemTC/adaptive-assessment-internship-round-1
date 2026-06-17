"""Silent evaluation layer for the voice tool (Layers 5+6 of the adaptive loop).

After a voice interview ends, this module assembles the transcript, decides
whether it is gradeable (flagging timed-out / failed / empty / low-confidence
responses), grades clean transcripts with the kernel LLM gateway, persists the
result to ``grade_results``, and hands the response to the memory agent to
extract an evidence card.

Nothing here is ever surfaced to the learner — grading is silent by law. The
public entry point :func:`evaluate_voice_response` never raises; failures are
returned as flagged outputs with ``flag_reason="failed"``.
"""

import json
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_litellm import ChatLiteLLM
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agent.memory_agent import run_memory_agent
from app.core.database import async_session
from app.core.llm import get_llm
from app.core.logging import get_logger
from app.features.voice.models import VoiceSession, VoiceTranscript
from app.features.voice.schemas import (
    TranscriptFlag,
    VoiceAdaptiveInput,
    VoiceAdaptiveOutput,
)
from app.sessions.models import GradeResult
from app.shared.schemas.memory import (
    DimensionSignals,
    RubricDimension,
    RubricScores,
)

logger = get_logger(__name__)

#: Average STT confidence below which a transcript is flagged as unreliable.
_LOW_CONFIDENCE_THRESHOLD: float = 0.65

#: Minimum non-whitespace character count for a transcript to be gradeable.
_MIN_TRANSCRIPT_CHARS: int = 10

#: Rubric overall score at/above which a response is considered passing.
_PASS_THRESHOLD: float = 0.5


async def get_transcript_text(
    voice_session_id: int,
    db: AsyncSession,
) -> tuple[str, float]:
    """Concatenate a session's transcript chunks and average their confidence.

    Args:
        voice_session_id: Primary key of the owning voice session.
        db: Active async database session.

    Returns:
        A ``(full_text, average_confidence)`` tuple. ``full_text`` joins every
        chunk's text in ``chunk_index`` order; ``average_confidence`` is the mean
        of the reported ``speaker_confidence`` values. Returns ``("", 0.0)`` when
        the session has no transcript rows.
    """
    result = await db.execute(
        select(VoiceTranscript)
        .where(VoiceTranscript.voice_session_id == voice_session_id)
        .order_by(VoiceTranscript.chunk_index)
    )
    rows = result.scalars().all()

    if not rows:
        logger.info(
            "transcript_loaded",
            voice_session_id=voice_session_id,
            chars=0,
            avg_confidence=0.0,
        )
        return "", 0.0

    text = " ".join(row.transcript_text for row in rows).strip()
    confidences = [
        row.speaker_confidence for row in rows if row.speaker_confidence is not None
    ]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

    logger.info(
        "transcript_loaded",
        voice_session_id=voice_session_id,
        chars=len(text),
        avg_confidence=avg_conf,
    )
    return text, avg_conf


def _detect_flag(
    transcript: str,
    avg_confidence: float,
    session_status: str,
) -> Optional[TranscriptFlag]:
    """Decide whether a transcript should be excluded from grading.

    Checked in priority order: ``timed_out`` -> ``failed`` -> ``empty_transcript``
    -> ``low_confidence`` -> clean.

    Args:
        transcript: The assembled transcript text.
        avg_confidence: Mean STT confidence across chunks.
        session_status: Lifecycle status of the voice session.

    Returns:
        The matching :data:`~app.features.voice.schemas.TranscriptFlag`, or
        ``None`` if the transcript is clean and gradeable.
    """
    if session_status == "timed_out":
        return "timed_out"
    if session_status == "failed":
        return "failed"
    if len(transcript.replace(" ", "")) < _MIN_TRANSCRIPT_CHARS:
        return "empty_transcript"
    if avg_confidence < _LOW_CONFIDENCE_THRESHOLD:
        return "low_confidence"
    return None


def _build_dimension_signals(rubric: RubricScores) -> DimensionSignals:
    """Convert rubric dimension scores to boolean engagement signals.

    A dimension is considered engaged when its rubric score exceeds ``0.3``.

    Args:
        rubric: The rubric scores produced by the LLM grader.

    Returns:
        The :class:`~app.shared.schemas.memory.DimensionSignals` for the response.
    """
    mapping = {d.name: d.score > 0.3 for d in rubric.dimensions}
    return DimensionSignals(
        thinking=mapping.get("thinking", False),
        soft=mapping.get("soft", False),
        work=mapping.get("work", False),
        digital_ai=mapping.get("digital_ai", False),
        growth=mapping.get("growth", False),
    )


async def _grade_transcript_with_llm(
    question_text: str,
    transcript: str,
    difficulty: str,
    llm: ChatLiteLLM,
) -> RubricScores:
    """Grade a voice transcript against a rubric using the kernel LLM gateway.

    Args:
        question_text: The interview question that was posed.
        transcript: The learner's assembled transcript text.
        difficulty: Difficulty tier the question targeted.
        llm: Configured LLM instance from the kernel factory.

    Returns:
        The parsed :class:`~app.shared.schemas.memory.RubricScores`. On any
        failure a default rubric with ``overall=0.0`` is returned instead of
        raising.
    """
    system = (
        "You are a technical interview evaluator. Grade a voice response.\n"
        "Return ONLY valid JSON — no markdown, no code fences, no explanation."
    )

    human = f"""Question: {question_text}
Difficulty: {difficulty}
Transcript: {transcript}

Return this exact JSON structure:
{{
  "dimensions": [
    {{"name": "thinking", "score": 0.0, "feedback": "one concise sentence"}},
    {{"name": "soft", "score": 0.0, "feedback": "one concise sentence"}},
    {{"name": "work", "score": 0.0, "feedback": "one concise sentence"}},
    {{"name": "growth", "score": 0.0, "feedback": "one concise sentence"}}
  ],
  "overall": 0.0
}}
Scores: 0.0 = no evidence, 1.0 = excellent. digital_ai omitted unless the \
question explicitly targets it."""

    try:
        response = await llm.ainvoke(
            [
                SystemMessage(content=system),
                HumanMessage(content=human),
            ]
        )

        raw_content = response.content
        if isinstance(raw_content, list):
            # Kimi K2 reasoning model: returns thinking blocks followed
            # by the actual answer as a plain string at the end of the list
            content = ""
            for item in reversed(raw_content):
                if isinstance(item, str) and item.strip():
                    content = item.strip()
                    break
                elif isinstance(item, dict) and item.get("type") == "text":
                    candidate = item.get("text", "").strip()
                    if candidate:
                        content = candidate
                        break
        else:
            content = str(raw_content).strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        parsed = json.loads(content)
        return RubricScores(
            dimensions=[RubricDimension(**d) for d in parsed["dimensions"]],
            overall=parsed["overall"],
        )

    except Exception as e:  # noqa: BLE001 - grading must degrade, never raise
        logger.error("llm_grading_failed", error=str(e))
        return RubricScores(
            dimensions=[
                RubricDimension(
                    name="error", score=0.0, feedback="LLM grading unavailable"
                )
            ],
            overall=0.0,
        )


async def _write_grade_result(
    session_id: str,
    voice_session_id: int,
    question_index: int,
    rubric: RubricScores,
    db: AsyncSession,
) -> int:
    """Persist a rubric result to ``grade_results`` and return its new id.

    Args:
        session_id: Owning assessment session identifier.
        voice_session_id: PK of the voice session that produced the response.
        question_index: Zero-based position in the assessment blueprint.
        rubric: The rubric scores to persist.
        db: Active async database session.

    Returns:
        The surrogate primary key of the inserted ``grade_results`` row.
    """
    row = GradeResult(
        session_id=session_id,  # FK deferred until assessment_sessions table exists
        tool_type="voice",
        tool_session_id=voice_session_id,
        question_index=question_index,
        rubric_scores=rubric.model_dump_json(),
        llm_judge_score=None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    logger.info("grade_result_written", grade_result_id=row.id)
    return row.id


async def evaluate_voice_response(
    input_data: VoiceAdaptiveInput,
) -> VoiceAdaptiveOutput:
    """Evaluate one voice response: flag, grade, persist, and extract memory.

    This is the entry point for the silent evaluation layer (Layers 5+6). It
    loads the transcript, flags ungradeable responses, grades clean ones with
    the LLM, writes a ``grade_results`` row, and runs the memory agent. It never
    raises; an unexpected failure is reported as a flagged output.

    Args:
        input_data: The evaluation request for a single voice response.

    Returns:
        A :class:`~app.features.voice.schemas.VoiceAdaptiveOutput` describing the
        outcome. Never shown to the learner.
    """
    async with async_session() as db:
        # 1. Load the voice session.
        voice_session = await db.get(VoiceSession, input_data.voice_session_id)
        if not voice_session:
            logger.error(
                "voice_session_not_found",
                voice_session_id=input_data.voice_session_id,
            )
            return VoiceAdaptiveOutput(
                session_id=input_data.session_id,
                voice_session_id=input_data.voice_session_id,
                question_index=input_data.question_index,
                transcript="",
                average_confidence=0.0,
                flagged=True,
                flag_reason="failed",
            )

        # 2. Assemble the transcript.
        transcript, avg_confidence = await get_transcript_text(
            input_data.voice_session_id, db
        )

        # 3. Decide whether the transcript is gradeable.
        flag = _detect_flag(transcript, avg_confidence, voice_session.status)
        flagged = flag is not None

        # 4. Grade clean transcripts; skip the LLM entirely when flagged.
        if not flagged:
            llm = get_llm()
            rubric = await _grade_transcript_with_llm(
                input_data.question_text,
                transcript,
                input_data.target_difficulty,
                llm,
            )
        else:
            logger.info(
                "transcript_flagged",
                reason=flag,
                voice_session_id=input_data.voice_session_id,
            )
            rubric = RubricScores(
                dimensions=[
                    RubricDimension(
                        name="flagged", score=0.0, feedback=f"Flagged: {flag}"
                    )
                ],
                overall=0.0,
            )

        # 5. Persist the rubric result.
        grade_result_id = await _write_grade_result(
            input_data.session_id,
            input_data.voice_session_id,
            input_data.question_index,
            rubric,
            db,
        )

        # 6. Record an evidence breadcrumb for the silent layer.
        evidence_summary = (
            f"Voice response flagged ({flag}). No gradeable content."
            if flagged
            else (
                f"Learner answered a {input_data.target_difficulty} question. "
                f"Overall rubric score: {rubric.overall:.2f}. "
                + (rubric.dimensions[0].feedback if rubric.dimensions else "")
            )
        )
        logger.info(
            "voice_evidence_summary",
            voice_session_id=input_data.voice_session_id,
            summary=evidence_summary,
        )

        # 7. Extract a memory card (Layer 6).
        new_card, memory_summary = await run_memory_agent(
            session_id=input_data.session_id,
            tool_type="voice",
            question_index=input_data.question_index,
            question_text=input_data.question_text,
            learner_response=transcript if transcript else "[no response]",
            rubric_scores_json=rubric.model_dump_json(),
            passed=rubric.overall >= _PASS_THRESHOLD,
            difficulty=input_data.target_difficulty,
        )

    return VoiceAdaptiveOutput(
        session_id=input_data.session_id,
        voice_session_id=input_data.voice_session_id,
        question_index=input_data.question_index,
        transcript=transcript,
        average_confidence=avg_confidence,
        flagged=flagged,
        flag_reason=flag,
        grade_result_id=grade_result_id,
        memory_card_id=new_card.id if new_card else None,
        memory_summary=memory_summary,
    )
