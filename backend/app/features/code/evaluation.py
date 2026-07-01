"""Layer 2 — Memory card extraction.

Turns one graded submission into an evidence card via the shared memory agent
(Qdrant upsert included). Persists the coding-tool ``code_memory_cards`` detail
row linked to the platform ``memory_cards`` row.
"""

from __future__ import annotations

import json
from typing import cast

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agent.memory_agent import run_memory_agent
from app.core.logging import get_logger
from app.features.code.models import CodeChallenge, CodeMemoryCard, CodeSubmission
from app.sessions.models import GradeResult, MemoryCard
from app.shared.schemas.memory import (
    DifficultyLevel,
    MemoryCardRead,
    RubricScores,
)

_logger = get_logger(__name__)

TOOL_TYPE = "coding"


def _dimension_feedback(rubric: RubricScores, name: str) -> str:
    for dim in rubric.dimensions:
        if dim.name == name:
            return dim.feedback
    return ""


def _dimension_score(rubric: RubricScores, name: str, default: float = 0.0) -> float:
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
    """Extract a memory card from a graded code submission via the memory agent."""
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

    challenge = await db.get(CodeChallenge, submission.challenge_id)
    question_text = (
        f"{challenge.title}\n\n{challenge.description}"
        if challenge is not None
        else "Coding challenge"
    )

    rubric = RubricScores.model_validate_json(grade.rubric_scores)
    sandbox_score = _dimension_score(rubric, "correctness")
    approach_feedback = _dimension_feedback(rubric, "approach")
    efficiency_feedback = _dimension_feedback(rubric, "efficiency")
    passed = bool(submission.passed)
    metadata = (
        json.loads(submission.grading_metadata) if submission.grading_metadata else {}
    )
    structured_test_results = metadata.get("all_test_results") or metadata.get(
        "test_results", []
    )

    new_card, _memory_summary = await run_memory_agent(
        session_id=session_id,
        tool_type=TOOL_TYPE,
        question_index=question_index,
        question_text=question_text,
        learner_response=submission.submitted_code,
        rubric_scores_json=grade.rubric_scores,
        passed=passed,
        difficulty=cast(DifficultyLevel, difficulty),
    )
    if new_card is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory agent failed to extract code evidence card",
        )

    detail = CodeMemoryCard(
        session_id=session_id,
        question_index=question_index,
        submission_id=submission.id or 0,
        memory_card_id=new_card.id,
        sandbox_score=sandbox_score,
        overall_rubric_score=rubric.overall,
        test_results=json.dumps(structured_test_results),
        approach_feedback=approach_feedback,
        efficiency_feedback=efficiency_feedback,
    )
    db.add(detail)
    await db.flush()

    memory_card = await db.get(MemoryCard, new_card.id)
    if memory_card is not None:
        await db.refresh(memory_card)
        created_at = memory_card.created_at
    else:
        created_at = new_card.created_at

    _logger.info(
        "code_memory_card_extracted",
        session_id=session_id,
        question_index=question_index,
        memory_card_id=new_card.id,
        passed=passed,
    )
    return MemoryCardRead(
        id=new_card.id,
        session_id=new_card.session_id,
        tool_type=new_card.tool_type,
        question_index=new_card.question_index,
        difficulty=new_card.difficulty,
        evidence_summary=new_card.evidence_summary,
        dimension_signals=new_card.dimension_signals,
        passed=new_card.passed,
        created_at=created_at,
    )


async def refresh_memory_card_for_grade(
    db: AsyncSession,
    grade_result_id: int,
    difficulty: str,
) -> None:
    """Update code detail + platform evidence summary after deferred LLM grading."""
    del difficulty  # retained for call-site compatibility
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

    detail = (
        await db.exec(
            select(CodeMemoryCard).where(
                CodeMemoryCard.submission_id == (submission.id or 0)
            )
        )
    ).first()
    if detail is None:
        return

    rubric = RubricScores.model_validate_json(grade.rubric_scores)
    sandbox_score = _dimension_score(rubric, "correctness")
    approach_feedback = _dimension_feedback(rubric, "approach")
    efficiency_feedback = _dimension_feedback(rubric, "efficiency")
    evidence_summary = _build_evidence_summary(
        passed=bool(submission.passed),
        sandbox_score=sandbox_score,
        approach_feedback=approach_feedback,
        efficiency_feedback=efficiency_feedback,
    )

    detail.sandbox_score = sandbox_score
    detail.overall_rubric_score = rubric.overall
    detail.approach_feedback = approach_feedback
    detail.efficiency_feedback = efficiency_feedback
    db.add(detail)

    memory_card = await db.get(MemoryCard, detail.memory_card_id)
    if memory_card is not None:
        memory_card.evidence_summary = evidence_summary
        db.add(memory_card)

    await db.flush()
    _logger.info(
        "code_memory_card_refreshed",
        grade_result_id=grade_result_id,
        submission_id=submission.id,
    )


__all__ = ["extract_memory_card", "refresh_memory_card_for_grade"]
