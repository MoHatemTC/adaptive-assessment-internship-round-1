"""Layer 4 — Adaptation.

Reads the session's ``skill_dimension_scores`` (and the ``assessment_sessions``
blueprint) and produces an :class:`AdaptiveContract` describing the *next*
question for the Generator Agent. This layer performs **no** database write —
the contract is a transient output passed straight to the generator.
"""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logging import get_logger
from app.sessions.models import AssessmentSession, SkillDimensionScore
from app.shared.schemas.memory import (
    AdaptiveContract,
    DifficultyLevel,
    DimensionName,
    DimensionScore,
)

_logger = get_logger(__name__)

TOOL_TYPE = "coding"

#: Stop the coding loop once this many questions have been answered.
_MAX_QUESTIONS = 5

#: Score thresholds (on a 1–10 scale) for the next question's difficulty.
_ADVANCED_AT = 8
_INTERMEDIATE_AT = 5

_ENGAGED_DIMENSIONS: tuple[DimensionName, ...] = ("thinking", "work", "digital_ai")


def _mean_int(values: list[int]) -> int | None:
    """Return the rounded integer mean of ``values``, or ``None`` if empty."""
    if not values:
        return None
    return max(1, min(10, round(sum(values) / len(values))))


def _difficulty_for(avg: int | None) -> DifficultyLevel:
    """Map an average engaged score to the next question's difficulty tier."""
    if avg is None:
        return "beginner"
    if avg >= _ADVANCED_AT:
        return "advanced"
    if avg >= _INTERMEDIATE_AT:
        return "intermediate"
    return "beginner"


async def compute_adaptive_contract(
    db: AsyncSession,
    session_id: str,
    assessment_id: str,
) -> AdaptiveContract:
    """Compute the adaptive contract for the next question.

    Aggregates all ``skill_dimension_scores`` rows for the session into
    cumulative dimension scores, picks the next difficulty from the engaged
    average, targets the weakest engaged dimension, and decides whether to
    stop. No row is written.

    Args:
        db: Active async database session.
        session_id: Platform assessment session UUID.
        assessment_id: Parent assessment identifier (passed through to context).

    Returns:
        A transient :class:`AdaptiveContract` for the Generator Agent.
    """
    rows = (
        await db.exec(
            select(SkillDimensionScore)
            .where(SkillDimensionScore.session_id == session_id)
            .order_by(SkillDimensionScore.question_index)
        )
    ).all()

    session = await db.get(AssessmentSession, session_id)
    session_completed = session is not None and session.status in {"completed", "expired"}

    per_dim: dict[DimensionName, list[int]] = {dim: [] for dim in _ENGAGED_DIMENSIONS}
    for row in rows:
        for dim in _ENGAGED_DIMENSIONS:
            value = getattr(row, dim)
            if value is not None:
                per_dim[dim].append(int(value))

    cumulative = DimensionScore(
        thinking=_mean_int(per_dim["thinking"]),
        work=_mean_int(per_dim["work"]),
        digital_ai=_mean_int(per_dim["digital_ai"]),
        soft=None,
        growth=None,
    )

    engaged_means = {
        dim: _mean_int(per_dim[dim])
        for dim in _ENGAGED_DIMENSIONS
        if _mean_int(per_dim[dim]) is not None
    }
    avg_engaged = _mean_int([m for m in engaged_means.values() if m is not None])

    focus_dimension: DimensionName | None = None
    if engaged_means:
        focus_dimension = min(engaged_means, key=lambda d: engaged_means[d])  # type: ignore[arg-type]

    answered = len({row.question_index for row in rows})
    next_index = (max((row.question_index for row in rows), default=-1)) + 1
    stop = session_completed or answered >= _MAX_QUESTIONS

    if stop:
        memory_summary = (
            f"Coding loop complete after {answered} question(s); "
            f"engaged average {avg_engaged or 'n/a'}/10."
        )
    elif avg_engaged is None:
        memory_summary = "No coding evidence yet; starting at beginner difficulty."
    else:
        memory_summary = (
            f"After {answered} question(s) the learner averages {avg_engaged}/10 on "
            f"engaged dimensions; next focus on '{focus_dimension}'."
        )

    contract = AdaptiveContract(
        session_id=session_id,
        question_index=next_index,
        tool_type=TOOL_TYPE,
        difficulty=_difficulty_for(avg_engaged),
        focus_dimension=focus_dimension,
        stop=stop,
        memory_summary=memory_summary,
        cumulative_scores=cumulative,
    )

    _logger.info(
        "code_adaptive_contract_computed",
        session_id=session_id,
        assessment_id=assessment_id,
        next_index=next_index,
        difficulty=contract.difficulty,
        stop=stop,
        focus=focus_dimension,
    )
    return contract


__all__ = ["compute_adaptive_contract"]
