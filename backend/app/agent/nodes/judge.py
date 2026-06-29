"""LLM judge over grade_results — Sprint 4 stretch (integration stub).

Karim's tool loops write ``grade_results`` rows; this module aggregates them
into ``llm_judge_score`` and a narrative for radar/email after admin approval.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logging import get_logger
from app.sessions.models import GradeResult

_logger = get_logger(__name__)


@dataclass(frozen=True)
class SessionJudgeResult:
    """Outcome of judging one completed session."""

    session_id: str
    llm_judge_score: float | None
    narrative: str
    grade_result_count: int


def _overall_from_rubric(raw: str) -> float | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    overall = payload.get("overall")
    return float(overall) if isinstance(overall, (int, float)) else None


async def run_session_judge(
    db: AsyncSession,
    session_id: str,
    *,
    include_proctoring: bool = True,
) -> SessionJudgeResult:
    """Aggregate grade_results for a session (LLM call wired in Sprint 4 stretch)."""
    rows = (
        await db.exec(
            select(GradeResult)
            .where(GradeResult.session_id == session_id)
            .order_by(GradeResult.question_index)
        )
    ).scalars().all()

    if not rows:
        return SessionJudgeResult(
            session_id=session_id,
            llm_judge_score=None,
            narrative="No graded tool responses yet.",
            grade_result_count=0,
        )

    scores = [_overall_from_rubric(row.rubric_scores) for row in rows]
    scores = [s for s in scores if s is not None]
    avg = round(sum(scores) / len(scores), 2) if scores else None
    narrative = (
        f"Aggregated {len(rows)} tool result(s)"
        + (f"; mean score {avg}." if avg is not None else ".")
    )
    if include_proctoring:
        narrative += " Proctoring summary will be merged in the LLM judge pass."

    _logger.info(
        "session_judge_stub",
        session_id=session_id,
        grade_result_count=len(rows),
        llm_judge_score=avg,
    )
    return SessionJudgeResult(
        session_id=session_id,
        llm_judge_score=avg,
        narrative=narrative,
        grade_result_count=len(rows),
    )


async def persist_session_judge_result(
    db: AsyncSession,
    result: SessionJudgeResult,
) -> None:
    """Write judge output onto the latest grade_results row."""
    if result.llm_judge_score is None:
        return
    row = (
        await db.exec(
            select(GradeResult)
            .where(GradeResult.session_id == result.session_id)
            .order_by(GradeResult.question_index.desc())
        )
    ).scalars().first()
    if row is None:
        return
    row.llm_judge_score = result.llm_judge_score
    db.add(row)
    await db.flush()


__all__ = ["SessionJudgeResult", "persist_session_judge_result", "run_session_judge"]
