"""Layer 3 — aggregate memory cards into learner analysis snapshots."""

from __future__ import annotations

import json
from collections import defaultdict

from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.code.adaptive_schemas import LearnerCodeAnalysis
from app.features.code.evaluation_memory import load_memory_cards
from app.features.code.models import CodeMemoryCard

# Map rubric dimension signals → blueprint skill dimensions (v1 deterministic).
_DIMENSION_TO_SKILL: dict[str, list[str]] = {
    "problem_solving": ["correctness", "completeness"],
    "syntax": ["code_quality", "documentation"],
    "algorithms": ["performance", "creativity"],
}

_STRONG_PASS_THRESHOLD = 0.8
_WEAK_PASS_THRESHOLD = 0.5
_RECENCY_DECAY = 0.85


def _weighted_average(values: list[tuple[float, float]]) -> float:
    if not values:
        return 0.0
    total_weight = sum(weight for _, weight in values)
    if total_weight <= 0:
        return 0.0
    return round(sum(value * weight for value, weight in values) / total_weight, 3)


def analyze_memory_cards(
    cards: list[CodeMemoryCard],
    *,
    skill_dimensions: list[str] | None = None,
) -> LearnerCodeAnalysis:
    """Deterministic aggregation over memory cards (recent turns weighted higher)."""
    if not cards:
        dimensions = skill_dimensions or list(_DIMENSION_TO_SKILL.keys())
        return LearnerCodeAnalysis(
            dimension_estimates={dim: 0.0 for dim in dimensions},
            strong_problem_types=[],
            weak_problem_types=[],
            average_pass_rate=0.0,
            average_efficiency=0.0,
            average_rubric_score=0.0,
            turns_completed=0,
        )

    n = len(cards)
    pass_values: list[tuple[float, float]] = []
    efficiency_values: list[tuple[float, float]] = []
    rubric_values: list[tuple[float, float]] = []
    type_pass: dict[str, list[tuple[float, float]]] = defaultdict(list)
    signal_values: dict[str, list[tuple[float, float]]] = defaultdict(list)

    for index, card in enumerate(cards):
        weight = _RECENCY_DECAY ** (n - 1 - index)
        pass_values.append((card.pass_rate, weight))
        efficiency_values.append((card.efficiency, weight))
        rubric_values.append((card.rubric_score, weight))
        type_pass[card.problem_type].append((card.pass_rate, weight))

        signals = json.loads(card.dimension_signals_json)
        for signal_name, value in signals.items():
            signal_values[signal_name].append((float(value), weight))

    dimension_targets = skill_dimensions or list(_DIMENSION_TO_SKILL.keys())
    dimension_estimates: dict[str, float] = {}
    for skill in dimension_targets:
        sources = _DIMENSION_TO_SKILL.get(skill, [])
        if not sources:
            dimension_estimates[skill] = 0.0
            continue
        parts = [
            _weighted_average(signal_values.get(source, []))
            for source in sources
            if signal_values.get(source)
        ]
        dimension_estimates[skill] = round(sum(parts) / len(parts), 3) if parts else 0.0

    strong_types: list[str] = []
    weak_types: list[str] = []
    for problem_type, samples in type_pass.items():
        avg = _weighted_average(samples)
        if avg >= _STRONG_PASS_THRESHOLD:
            strong_types.append(problem_type)
        elif avg < _WEAK_PASS_THRESHOLD:
            weak_types.append(problem_type)

    return LearnerCodeAnalysis(
        dimension_estimates=dimension_estimates,
        strong_problem_types=sorted(strong_types),
        weak_problem_types=sorted(weak_types),
        average_pass_rate=_weighted_average(pass_values),
        average_efficiency=_weighted_average(efficiency_values),
        average_rubric_score=_weighted_average(rubric_values),
        turns_completed=n,
    )


async def analyze_session(
    db: AsyncSession,
    code_session_id: str,
    *,
    skill_dimensions: list[str] | None = None,
) -> LearnerCodeAnalysis:
    cards = await load_memory_cards(db, code_session_id)
    return analyze_memory_cards(cards, skill_dimensions=skill_dimensions)
