"""Build five-dimension radar reports from platform grading tables."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logging import get_logger
from app.reports.schemas import DimensionRadarPoint, SessionRadarReport, dimension_label
from app.sessions.models import MemoryCard, SkillDimensionScore
from app.shared.schemas.memory import DimensionName

_logger = get_logger(__name__)

_ALL_DIMENSIONS: tuple[DimensionName, ...] = (
    "thinking",
    "soft",
    "work",
    "digital_ai",
    "growth",
)


def aggregate_dimension_scores(
    rows: list[SkillDimensionScore],
) -> dict[DimensionName, int | None]:
    """Average non-null scores per dimension across all session rows."""
    aggregated: dict[DimensionName, int | None] = {}
    for dim in _ALL_DIMENSIONS:
        values = [getattr(row, dim) for row in rows if getattr(row, dim) is not None]
        if not values:
            aggregated[dim] = None
        else:
            aggregated[dim] = max(1, min(10, round(sum(values) / len(values))))
    return aggregated


def _overall_score(scores: dict[DimensionName, int | None]) -> int | None:
    values = [value for value in scores.values() if value is not None]
    if not values:
        return None
    return max(1, min(10, round(sum(values) / len(values))))


def _strengths_and_growth(
    scores: dict[DimensionName, int | None],
) -> tuple[list[str], list[str]]:
    strengths: list[str] = []
    growth_areas: list[str] = []
    for dim, score in scores.items():
        if score is None:
            continue
        label = dimension_label(dim)
        if score >= 7:
            strengths.append(label)
        elif score <= 4:
            growth_areas.append(label)
    return strengths, growth_areas


def _build_summary(
    *,
    overall: int | None,
    strengths: list[str],
    growth_areas: list[str],
    tools_used: list[str],
) -> str:
    if overall is None:
        return "Not enough assessed responses yet to generate a skill profile."

    tools = ", ".join(tools_used) if tools_used else "assessment tools"
    parts = [
        f"Overall skill profile: {overall}/10 across evidence from {tools}.",
    ]
    if strengths:
        parts.append(f"Strengths: {', '.join(strengths)}.")
    if growth_areas:
        parts.append(f"Areas to develop: {', '.join(growth_areas)}.")
    return " ".join(parts)


async def build_session_radar_report(
    db: AsyncSession,
    session_id: str,
) -> SessionRadarReport:
    """Aggregate platform scores and memory highlights into a radar report."""
    score_rows = (
        await db.scalars(
            select(SkillDimensionScore)
            .where(SkillDimensionScore.session_id == session_id)
            .order_by(SkillDimensionScore.question_index)
        )
    ).all()

    memory_rows = (
        await db.scalars(
            select(MemoryCard)
            .where(MemoryCard.session_id == session_id)
            .order_by(MemoryCard.question_index.desc())
            .limit(5)
        )
    ).all()

    aggregated = aggregate_dimension_scores(list(score_rows))
    overall = _overall_score(aggregated)
    strengths, growth_areas = _strengths_and_growth(aggregated)

    tools_used = sorted({row.tool_type for row in score_rows})
    if not tools_used:
        tools_used = sorted({row.tool_type for row in memory_rows})

    question_keys = {(row.tool_type, row.question_index) for row in score_rows}
    questions_answered = len(question_keys) if question_keys else len(memory_rows)

    highlights = [
        row.evidence_summary.strip()
        for row in reversed(list(memory_rows))
        if row.evidence_summary and row.evidence_summary.strip()
    ][:5]

    dimensions = [
        DimensionRadarPoint(
            name=dim,
            label=dimension_label(dim),
            score=aggregated[dim],
        )
        for dim in _ALL_DIMENSIONS
    ]

    report = SessionRadarReport(
        session_id=session_id,
        dimensions=dimensions,
        overall_score=overall,
        questions_answered=questions_answered,
        tools_used=tools_used,
        strengths=strengths,
        growth_areas=growth_areas,
        evidence_highlights=highlights,
        summary=_build_summary(
            overall=overall,
            strengths=strengths,
            growth_areas=growth_areas,
            tools_used=tools_used,
        ),
        generated_at=datetime.now(timezone.utc),
    )

    _logger.info(
        "radar_report_built",
        session_id=session_id,
        overall_score=overall,
        questions_answered=questions_answered,
        tools=tools_used,
    )
    return report
