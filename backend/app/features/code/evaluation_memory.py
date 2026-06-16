"""Layer 2 — Memory card extraction.

Turns one graded submission into an evidence card. Writes the shared
``memory_cards`` row (input to Layer 3) plus the coding-tool ``code_memory_cards``
detail row, and returns a :class:`MemoryCardRead`.

The coding tool always engages the ``thinking``, ``work`` and ``digital_ai``
dimensions; ``soft`` and ``growth`` are not exercised by a code submission.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logging import get_logger
from app.features.code.models import CodeMemoryCard, CodeSubmission
from app.sessions.models import GradeResult, MemoryCard
from app.shared.schemas.memory import (
    DimensionSignals,
    MemoryCardCreate,
    MemoryCardRead,
    RubricScores,
)

_logger = get_logger(__name__)

TOOL_TYPE = "coding"


def _dimension_feedback(rubric: RubricScores, name: str) -> str:
    """Return the feedback for a named rubric dimension, or empty string."""
    for dim in rubric.dimensions:
        if dim.name == name:
            return dim.feedback
    return ""


def _dimension_score(rubric: RubricScores, name: str, default: float = 0.0) -> float:
    """Return the score for a named rubric dimension, or ``default``."""
    for dim in rubric.dimensions:
        if dim.name == name:
            return dim.score
    return default


def _build_evidence_summary(
    *,
    passed: bool,
    sandbox_score: float,
    approach_feedback: str,
    efficiency_feedback: str,
) -> str:
    """Compose a concise, human-readable evidence summary for the card.

    Deterministic — derived from the Layer 1 rubric rather than a second LLM
    call, so memory extraction stays cheap and reproducible.
    """
    verdict = "passed" if passed else "did not pass"
    return (
        f"Submission {verdict} with sandbox correctness {sandbox_score:.0%}. "
        f"Approach: {approach_feedback or 'n/a'} "
        f"Efficiency: {efficiency_feedback or 'n/a'}"
    ).strip()


async def extract_memory_card(
    db: AsyncSession,
    session_id: str,
    question_index: int,
    grade_result_id: int,
    difficulty: str,
) -> MemoryCardRead:
    """Extract a memory card from a graded code submission.

    Reads the ``grade_results`` row and its originating submission, then writes
    one ``memory_cards`` row (platform) and one ``code_memory_cards`` row
    (coding detail), linked by ``memory_card_id``.

    Args:
        db: Active async database session.
        session_id: Platform assessment session UUID.
        question_index: Zero-based position in the assessment blueprint.
        grade_result_id: PK of the ``grade_results`` row produced by Layer 1.
        difficulty: Question difficulty — ``"beginner"``/``"intermediate"``/``"advanced"``.

    Returns:
        A :class:`MemoryCardRead` view of the persisted platform card.

    Raises:
        HTTPException: 404 if the grade result or its submission is missing.
    """
    grade = await db.get(GradeResult, grade_result_id)
    if grade is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Grade result not found"
        )

    submission = (
        await db.exec(
            select(CodeSubmission).where(CodeSubmission.id == grade.tool_session_id)
        )
    ).first()
    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found"
        )

    rubric = RubricScores.model_validate_json(grade.rubric_scores)
    sandbox_score = _dimension_score(rubric, "correctness")
    approach_feedback = _dimension_feedback(rubric, "approach")
    efficiency_feedback = _dimension_feedback(rubric, "efficiency")
    passed = bool(submission.passed)

    signals = DimensionSignals(thinking=True, soft=False, work=True, digital_ai=True, growth=False)
    evidence_summary = _build_evidence_summary(
        passed=passed,
        sandbox_score=sandbox_score,
        approach_feedback=approach_feedback,
        efficiency_feedback=efficiency_feedback,
    )

    # Validate the shared card shape (incl. difficulty literal) before persisting.
    card_in = MemoryCardCreate(
        session_id=session_id,
        tool_type=TOOL_TYPE,
        question_index=question_index,
        difficulty=difficulty,  # type: ignore[arg-type]
        evidence_summary=evidence_summary,
        dimension_signals=signals,
        passed=passed,
    )

    memory_card = MemoryCard(
        session_id=card_in.session_id,
        tool_type=card_in.tool_type,
        question_index=card_in.question_index,
        difficulty=card_in.difficulty,
        evidence_summary=card_in.evidence_summary,
        dimension_signals=card_in.dimension_signals.model_dump_json(),
        passed=card_in.passed,
    )
    db.add(memory_card)
    await db.flush()

    detail = CodeMemoryCard(
        session_id=session_id,
        question_index=question_index,
        submission_id=submission.id or 0,
        memory_card_id=memory_card.id,
        sandbox_score=sandbox_score,
        approach_feedback=approach_feedback,
        efficiency_feedback=efficiency_feedback,
    )
    db.add(detail)
    await db.flush()
    await db.refresh(memory_card)

    _logger.info(
        "code_memory_card_extracted",
        session_id=session_id,
        question_index=question_index,
        memory_card_id=memory_card.id,
        passed=passed,
    )
    return MemoryCardRead(
        id=memory_card.id,
        session_id=card_in.session_id,
        tool_type=card_in.tool_type,
        question_index=card_in.question_index,
        difficulty=card_in.difficulty,
        evidence_summary=card_in.evidence_summary,
        dimension_signals=card_in.dimension_signals,
        passed=card_in.passed,
        created_at=memory_card.created_at,
    )


__all__ = ["extract_memory_card"]
