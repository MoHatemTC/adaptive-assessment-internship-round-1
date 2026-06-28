"""Skill taxonomy analysis for the MCQ tool (Layer 7 of the adaptive loop).

Aggregates every MCQ memory card written for a session into per-dimension
ability estimates and persists a ``skill_dimension_scores`` row. Mirrors
:func:`app.features.voice.analysis.analyze_voice_session` exactly, so the
admin radar report aggregates MCQ sessions the same way it already aggregates
voice sessions. Nothing here is shown to the learner.
"""

import json
from typing import Any

from sqlalchemy import select

from app.core.database import async_session
from app.core.logging import get_logger
from app.sessions.models import MemoryCard, SkillDimensionScore

logger = get_logger(__name__)

#: The five skill dimensions tracked across every tool.
_DIMENSIONS = ["thinking", "soft", "work", "digital_ai", "growth"]


async def analyze_mcq_session(
    session_id: str,
    current_question_index: int,
) -> dict[str, Any]:
    """Aggregate a session's MCQ memory cards into dimension ability estimates.

    Tallies the boolean dimension signals across every MCQ memory card, computes
    a per-dimension engagement rate, derives an overall mastery level from the
    pass rate, and persists a :class:`SkillDimensionScore` row.

    Args:
        session_id: Owning assessment session identifier.
        current_question_index: Zero-based index of the question just answered.

    Returns:
        A dict with ``session_id``, ``total_cards``, per-dimension ``dimensions``
        stats, ``weakest_dimension``, ``strongest_dimension``, and
        ``mastery_level`` (``"low"``/``"medium"``/``"high"``).
    """
    async with async_session() as db:
        # 1. Load all MCQ memory cards for this session.
        stmt = (
            select(MemoryCard)
            .where(MemoryCard.session_id == session_id)
            .where(MemoryCard.tool_type == "mcq")
            .order_by(MemoryCard.question_index)
        )
        result = await db.execute(stmt)
        cards = result.scalars().all()

        if not cards:
            logger.info("no_mcq_cards_yet", session_id=session_id)
            return {
                "session_id": session_id,
                "total_cards": 0,
                "dimensions": {},
                "weakest_dimension": None,
                "strongest_dimension": None,
                "mastery_level": "low",
            }

        # 2. Tally dimension signals from each card's dimension_signals JSON.
        dimension_counts: dict[str, dict] = {
            dim: {"signal_count": 0, "total": 0} for dim in _DIMENSIONS
        }
        for card in cards:
            try:
                signals = json.loads(card.dimension_signals)
            except (json.JSONDecodeError, TypeError):
                continue
            for dim in dimension_counts:
                dimension_counts[dim]["total"] += 1
                if signals.get(dim, False):
                    dimension_counts[dim]["signal_count"] += 1

        # 3. Compute engagement rates.
        dimension_stats: dict[str, Any] = {}
        for dim, counts in dimension_counts.items():
            total = counts["total"]
            signal_count = counts["signal_count"]
            rate = signal_count / total if total > 0 else 0.0
            dimension_stats[dim] = {
                "signal_count": signal_count,
                "total": total,
                "rate": rate,
            }

        # 4. Weakest and strongest, considering only active dimensions.
        active = {d: s for d, s in dimension_stats.items() if s["total"] > 0}
        weakest = min(active, key=lambda d: active[d]["rate"]) if active else None
        strongest = max(active, key=lambda d: active[d]["rate"]) if active else None

        # 5. Overall mastery from the pass rate.
        passed = sum(1 for c in cards if c.passed)
        pass_rate = passed / len(cards)
        if pass_rate >= 0.7:
            mastery_level = "high"
        elif pass_rate >= 0.4:
            mastery_level = "medium"
        else:
            mastery_level = "low"

        # 6. Persist a SkillDimensionScore row (whole integers 1–10, or None).
        def rate_to_score(dim: str) -> int | None:
            if dimension_stats[dim]["total"] == 0:
                return None
            raw = round(dimension_stats[dim]["rate"] * 10)
            return max(1, min(10, raw if raw > 0 else 1))

        score_row = SkillDimensionScore(
            session_id=session_id,  # FK deferred until assessment_sessions table exists
            question_index=current_question_index,
            tool_type="mcq",
            thinking=rate_to_score("thinking"),
            soft=rate_to_score("soft"),
            work=rate_to_score("work"),
            digital_ai=rate_to_score("digital_ai"),
            growth=rate_to_score("growth"),
        )
        db.add(score_row)
        await db.commit()
        logger.info(
            "mcq_skill_scores_written",
            session_id=session_id,
            mastery_level=mastery_level,
        )

    return {
        "session_id": session_id,
        "total_cards": len(cards),
        "dimensions": dimension_stats,
        "weakest_dimension": weakest,
        "strongest_dimension": strongest,
        "mastery_level": mastery_level,
    }
