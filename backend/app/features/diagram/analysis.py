"""
Analysis layer for the diagram/image feature.

Responsibility: read all VisualMemoryCards for a session and collapse them
into a single, recency-weighted estimate per skill dimension, plus a
confidence band per dimension so the adaptation layer knows how much to
trust each estimate.

Consumes:  list[VisualMemoryCard] (fetched from Qdrant for a session)
Produces:  DimensionVector (consumed by adaptation.py)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from app.features.diagram.evaluation_memory import VisualMemoryCard
from app.features.diagram.grading import DIMENSIONS


HALF_LIFE_QUESTIONS = 3.0   # recency decay: card N questions ago has weight 0.5^(N/HALF_LIFE)
MIN_CARDS_FOR_FULL_CONFIDENCE = 3


@dataclass(frozen=True)
class DimensionEstimate:
    score: float          # 0-1, recency-weighted mean
    confidence: float     # 0-1, derived from sample count + score variance
    n_cards: int           # how many memory cards contributed to this dimension


@dataclass(frozen=True)
class DimensionVector:
    session_id: str
    estimates: dict[str, DimensionEstimate]   # keyed by DIMENSIONS
    computed_at: datetime

    def weakest_dimension(self) -> str:
        """Lowest score among dimensions with at least one observation;
        falls back to lowest confidence if all scores are tied."""
        scored = {d: e for d, e in self.estimates.items() if e.n_cards > 0}
        if not scored:
            return DIMENSIONS[0]
        return min(scored, key=lambda d: (scored[d].score, scored[d].confidence))


class MemoryCardReader(Protocol):
    async def fetch_cards(self, session_id: str) -> list[VisualMemoryCard]: ...


def _recency_weight(card_index_from_latest: int) -> float:
    """card_index_from_latest = 0 is the most recent card."""
    return 0.5 ** (card_index_from_latest / HALF_LIFE_QUESTIONS)


def _weighted_mean_and_variance(values: list[float], weights: list[float]) -> tuple[float, float]:
    total_w = sum(weights)
    if total_w == 0:
        return 0.0, 0.0
    mean = sum(v * w for v, w in zip(values, weights)) / total_w
    variance = sum(w * (v - mean) ** 2 for v, w in zip(values, weights)) / total_w
    return mean, variance


def _confidence_from(n_cards: int, variance: float) -> float:
    """More cards -> higher confidence. Higher variance -> lower confidence.
    Both terms in [0,1], geometric combination so either factor alone caps it."""
    sample_term = min(1.0, n_cards / MIN_CARDS_FOR_FULL_CONFIDENCE)
    variance_term = 1.0 / (1.0 + 4.0 * variance)   # variance=0 -> 1.0, variance=0.25 -> ~0.5
    return round(sample_term * variance_term, 3)


def aggregate_dimensions(session_id: str, cards: list[VisualMemoryCard]) -> DimensionVector:
    """Pure function — no I/O — so it's trivially unit-testable."""
    cards_newest_first = sorted(cards, key=lambda c: c.created_at, reverse=True)

    estimates: dict[str, DimensionEstimate] = {}
    for dim in DIMENSIONS:
        values, weights = [], []
        for idx, card in enumerate(cards_newest_first):
            if dim not in card.dimension_scores:
                continue
            values.append(card.dimension_scores[dim])
            weights.append(_recency_weight(idx))

        if not values:
            estimates[dim] = DimensionEstimate(score=0.0, confidence=0.0, n_cards=0)
            continue

        mean, variance = _weighted_mean_and_variance(values, weights)
        estimates[dim] = DimensionEstimate(
            score=round(mean, 3),
            confidence=_confidence_from(len(values), variance),
            n_cards=len(values),
        )

    return DimensionVector(
        session_id=session_id,
        estimates=estimates,
        computed_at=datetime.now(timezone.utc),
    )


async def analyze_session(session_id: str, reader: MemoryCardReader) -> DimensionVector:
    """Entry point called by the examiner agent before each next-question
    selection (Phase 2 -> Phase 3 handoff)."""
    cards = await reader.fetch_cards(session_id)
    return aggregate_dimensions(session_id, cards)