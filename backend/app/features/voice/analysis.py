"""Skill taxonomy analysis for the voice tool (Layer 7 of the adaptive loop).

Aggregates every voice memory card written for a session into per-dimension
ability estimates, derives an overall mastery level, and persists a
``skill_dimension_scores`` row. The output feeds the adaptation layer (Layer 8),
which selects the next question. Nothing here is shown to the learner.
"""

import json
from typing import Any

from sqlalchemy import select

from app.core.database import async_session
from app.core.logging import get_logger
from app.features.voice.models import VoiceSession
from app.sessions.models import MemoryCard, SkillDimensionScore

logger = get_logger(__name__)

#: The five skill dimensions tracked across every tool.
_DIMENSIONS = ["thinking", "soft", "work", "digital_ai", "growth"]


async def analyze_voice_session(
    session_id: str,
    current_question_index: int,
) -> dict[str, Any]:
    """Aggregate a session's voice memory cards into dimension ability estimates.

    Tallies the boolean dimension signals across every voice memory card, computes
    a per-dimension engagement rate, derives an overall mastery level from the
    pass rate, and persists a :class:`SkillDimensionScore` row.

    Args:
        session_id: Owning assessment session identifier.
        current_question_index: Zero-based index of the question just answered.

    Returns:
        A dict with ``session_id``, ``total_cards``, per-dimension ``dimensions``
        stats, ``weakest_dimension``, ``strongest_dimension``, ``mastery_level``
        (``"low"``/``"medium"``/``"high"``), and ``recommended_follow_up_depth``
        (``"simple"``/``"deep"``).
    """
    async with async_session() as db:
        # 1. Load all voice memory cards for this session.
        stmt = (
            select(MemoryCard)
            .where(MemoryCard.session_id == session_id)
            .where(MemoryCard.tool_type == "voice")
            .order_by(MemoryCard.question_index)
        )
        result = await db.execute(stmt)
        cards = result.scalars().all()

        # 2. Load previously asked question texts to prevent duplicate generation.
        q_stmt = (
            select(VoiceSession.question_text, VoiceSession.question_index)
            .where(VoiceSession.session_id == session_id)
            .where(VoiceSession.question_text.isnot(None))
            .order_by(VoiceSession.question_index)
        )
        q_result = await db.execute(q_stmt)
        prior_questions = [
            row[0] for row in q_result.fetchall()
            if row[0] and len(row[0].strip()) > 5
        ]
        logger.info(
            "prior_questions_loaded",
            session_id=session_id,
            count=len(prior_questions),
        )

        if not cards:
            logger.info("no_voice_cards_yet", session_id=session_id)
            return {
                "session_id": session_id,
                "total_cards": 0,
                "dimensions": {},
                "weakest_dimension": None,
                "strongest_dimension": None,
                "mastery_level": "low",
                "recommended_follow_up_depth": "simple",
                "prior_questions": prior_questions,
            }

        # 3. Tally dimension signals from each card's dimension_signals JSON.
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

        # 4. Compute engagement rates.
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

        # 5. Weakest and strongest, considering only active dimensions.
        active = {d: s for d, s in dimension_stats.items() if s["total"] > 0}
        weakest = min(active, key=lambda d: active[d]["rate"]) if active else None
        strongest = max(active, key=lambda d: active[d]["rate"]) if active else None

        # 6. Overall mastery from the pass rate.
        passed = sum(1 for c in cards if c.passed)
        pass_rate = passed / len(cards)
        if pass_rate >= 0.7:
            mastery_level = "high"
        elif pass_rate >= 0.4:
            mastery_level = "medium"
        else:
            mastery_level = "low"

        follow_up_depth = "deep" if mastery_level == "high" else "simple"

        # 7. Persist a SkillDimensionScore row (whole integers 1–10, or None).
        def rate_to_score(dim: str) -> int | None:
            if dimension_stats[dim]["total"] == 0:
                return None
            raw = round(dimension_stats[dim]["rate"] * 10)
            return max(1, min(10, raw if raw > 0 else 1))

        score_row = SkillDimensionScore(
            session_id=session_id,  # FK deferred until assessment_sessions table exists
            question_index=current_question_index,
            tool_type="voice",
            thinking=rate_to_score("thinking"),
            soft=rate_to_score("soft"),
            work=rate_to_score("work"),
            digital_ai=rate_to_score("digital_ai"),
            growth=rate_to_score("growth"),
        )
        db.add(score_row)
        await db.commit()
        logger.info(
            "skill_scores_written",
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
        "recommended_follow_up_depth": follow_up_depth,
        "prior_questions": prior_questions,
    }


async def get_voice_session_analysis(session_id: str) -> dict[str, Any]:
    """Read-only view of a session's current analysis state.

    Reads only already-persisted ``MemoryCard`` and ``SkillDimensionScore``
    rows. Never computes a fresh aggregation and never writes to the
    database — safe to call on every frontend poll, unlike
    :func:`analyze_voice_session`, which both aggregates and persists a new
    ``skill_dimension_scores`` row on every call.

    Args:
        session_id: Owning assessment session identifier.

    Returns:
        A dict with ``session_id``, ``card_count``, ``pass_rate``,
        ``mastery_level``, ``weakest_dimension``, ``question_count``, and
        ``recommended_follow_up_depth``. Cold-start values if no data exists.
    """
    async with async_session() as db:
        card_stmt = (
            select(MemoryCard)
            .where(MemoryCard.session_id == session_id)
            .where(MemoryCard.tool_type == "voice")
        )
        card_result = await db.execute(card_stmt)
        cards = card_result.scalars().all()

        card_count = len(cards)
        passed_count = sum(1 for card in cards if card.passed)
        pass_rate = passed_count / card_count if card_count > 0 else 0.0

        if card_count == 0:
            mastery_level = "unknown"
        elif pass_rate >= 0.7:
            mastery_level = "high"
        elif pass_rate <= 0.3:
            mastery_level = "low"
        else:
            mastery_level = "medium"
        follow_up_depth = "deep" if mastery_level == "high" else "simple"

        score_stmt = (
            select(SkillDimensionScore)
            .where(SkillDimensionScore.session_id == session_id)
            .where(SkillDimensionScore.tool_type == "voice")
            .order_by(SkillDimensionScore.question_index.desc())
        )
        score_result = await db.execute(score_stmt)
        score_rows = score_result.scalars().all()

        question_count = len(score_rows)
        weakest_dimension = None
        if score_rows:
            latest = score_rows[0]
            dim_scores = {
                dim: getattr(latest, dim)
                for dim in _DIMENSIONS
                if getattr(latest, dim) is not None
            }
            if dim_scores:
                weakest_dimension = min(dim_scores, key=lambda d: dim_scores[d])

    logger.info("voice_analysis_read", session_id=session_id, card_count=card_count)

    return {
        "session_id": session_id,
        "card_count": card_count,
        "pass_rate": pass_rate,
        "mastery_level": mastery_level,
        "weakest_dimension": weakest_dimension,
        "question_count": question_count,
        "recommended_follow_up_depth": follow_up_depth,
    }
