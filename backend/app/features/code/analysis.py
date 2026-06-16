"""Layer 3 — Skill taxonomy analysis.

Aggregates every ``memory_cards`` row for a session into a single
``skill_dimension_scores`` row. The coding tool engages ``thinking``, ``work``
and ``digital_ai``; ``soft`` and ``growth`` stay ``None`` (SQL NULL) because a
code submission does not exercise them.

Scores are whole integers 1–10 — never floats.
"""

from __future__ import annotations

import json

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logging import get_logger
from app.sessions.models import MemoryCard, SkillDimensionScore
from app.shared.schemas.memory import DimensionSignals, SkillDimensionScoreCreate

_logger = get_logger(__name__)

TOOL_TYPE = "coding"

#: Dimensions the coding tool can produce evidence for. Everything else is N/A.
_ENGAGED_DIMENSIONS = ("thinking", "work", "digital_ai")


def _score_from_pass_rate(pass_rate: float) -> int:
    """Map a pass rate in ``[0, 1]`` to a whole-integer skill score in ``[1, 10]``.

    Args:
        pass_rate: Fraction of memory cards that cleared the pass threshold.

    Returns:
        A whole integer in ``[1, 10]``.
    """
    score = round(1 + 9 * pass_rate)
    return max(1, min(10, int(score)))


async def analyse_session(
    db: AsyncSession,
    session_id: str,
    question_index: int,
) -> SkillDimensionScore:
    """Aggregate a session's memory cards into one skill-dimension row.

    Reads all coding ``memory_cards`` for ``session_id`` so far, derives a
    1–10 score for the engaged dimensions from the pass rate, and writes a
    single ``skill_dimension_scores`` row tagged with ``question_index``.

    Args:
        db: Active async database session.
        session_id: Platform assessment session UUID.
        question_index: Zero-based position of the question just answered.

    Returns:
        The persisted :class:`~app.sessions.models.SkillDimensionScore` row.
    """
    cards = (
        await db.exec(
            select(MemoryCard).where(
                MemoryCard.session_id == session_id,
                MemoryCard.tool_type == TOOL_TYPE,
            )
        )
    ).all()

    total = len(cards)
    passed = sum(1 for c in cards if c.passed)
    pass_rate = (passed / total) if total else 0.0

    # Only credit a dimension if at least one card actually engaged it.
    engaged: set[str] = set()
    for card in cards:
        signals = DimensionSignals.model_validate(json.loads(card.dimension_signals))
        for dim in _ENGAGED_DIMENSIONS:
            if getattr(signals, dim):
                engaged.add(dim)

    score = _score_from_pass_rate(pass_rate)
    dim_scores = {dim: (score if dim in engaged else None) for dim in _ENGAGED_DIMENSIONS}

    validated = SkillDimensionScoreCreate(
        session_id=session_id,
        question_index=question_index,
        tool_type=TOOL_TYPE,
        thinking=dim_scores["thinking"],
        work=dim_scores["work"],
        digital_ai=dim_scores["digital_ai"],
        soft=None,
        growth=None,
    )

    row = SkillDimensionScore(
        session_id=validated.session_id,
        question_index=validated.question_index,
        tool_type=validated.tool_type,
        thinking=validated.thinking,
        soft=validated.soft,
        work=validated.work,
        digital_ai=validated.digital_ai,
        growth=validated.growth,
    )
    db.add(row)
    await db.flush()

    _logger.info(
        "code_session_analysed",
        session_id=session_id,
        question_index=question_index,
        cards=total,
        pass_rate=round(pass_rate, 3),
        score=score,
    )
    return row


__all__ = ["analyse_session"]
