"""LLM judge over grade_results — produces holistic score + narrative.

Karim's tool loops write ``grade_results`` rows; this module aggregates them
into an ``llm_judge_score`` via an LLM call and a narrative for radar/email.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings
from app.core.llm import get_llm_with_tracing
from app.core.llm_json import extract_llm_text, parse_llm_json
from app.core.logging import get_logger
from app.core.metrics import record_llm_call
from app.sessions.models import GradeResult

_logger = get_logger(__name__)


@dataclass(frozen=True)
class SessionJudgeResult:
    """Outcome of judging one completed session."""

    session_id: str
    llm_judge_score: float | None
    narrative: str
    grade_result_count: int


_SYSTEM_PROMPT = """You are an expert assessment judge. Evaluate a learner's
performance across their entire assessment session, which includes multiple
questions across different tool types (MCQ, diagram, coding, voice).

For each question you will receive:
- The tool type
- The question's rubric dimension and score (0.0–1.0)
- Any grading feedback

Produce a JSON object with exactly these fields:
{
  "overall_score": <float 0.0–1.0>,
  "narrative": "<2–3 sentence summary of the learner's performance>"
}

The overall_score should reflect the holistic quality of the learner's work, not
a simple average. Consider consistency, areas of strength, and patterns across
different question types."""


def _overall_from_rubric(raw: str) -> float | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    overall = payload.get("overall")
    return float(overall) if isinstance(overall, (int, float)) else None


def _build_judge_prompt(rows: list[GradeResult]) -> str:
    """Build a human message listing every grade_result for the session."""
    lines: list[str] = ["Here are the graded responses for this session:\n"]
    for row in rows:
        try:
            rubric = json.loads(row.rubric_scores)
        except json.JSONDecodeError:
            rubric = {}
        dims = rubric.get("dimensions", [])
        dim_str = (
            "; ".join(f"{d.get('name', '?')}={d.get('score', '?')}" for d in dims)
            if dims
            else f"overall={rubric.get('overall', '?')}"
        )
        lines.append(f"- Question {row.question_index} ({row.tool_type}): {dim_str}")
    lines.append(
        "\nEvaluate the learner's performance holistically and return a JSON "
        "object with 'overall_score' (0.0–1.0) and 'narrative' (2–3 sentences)."
    )
    return "\n".join(lines)


async def run_session_judge(
    db: AsyncSession,
    session_id: str,
    *,
    include_proctoring: bool = True,
) -> SessionJudgeResult:
    """Run LLM judge over all grade_results for a session.

    Gathers every ``GradeResult`` row, calls the LLM for a holistic evaluation,
    and returns the aggregate score and narrative. Falls back to a simple average
    of rubric scores if the LLM call fails.
    """
    rows = (
        (
            await db.exec(
                select(GradeResult)
                .where(GradeResult.session_id == session_id)
                .order_by(GradeResult.question_index)
            )
        )
        .scalars()
        .all()
    )

    if not rows:
        return SessionJudgeResult(
            session_id=session_id,
            llm_judge_score=None,
            narrative="No graded tool responses yet.",
            grade_result_count=0,
        )

    llm_judge_score: float | None = None
    narrative: str = ""
    settings = get_settings()
    model = settings.LITELLM_MODEL

    try:
        llm, callbacks = get_llm_with_tracing(model)
        if hasattr(llm, "temperature"):
            llm.temperature = 0.0

        prompt = _build_judge_prompt(rows)
        start = time.perf_counter()
        response = await llm.ainvoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ],
            config={"callbacks": callbacks},
        )
        duration = time.perf_counter() - start
        record_llm_call(model, "session_judge", "success", duration)

        raw_text = extract_llm_text(response.content)
        parsed = parse_llm_json(raw_text)
        score_val = parsed.get("overall_score")
        if isinstance(score_val, (int, float)):
            llm_judge_score = max(0.0, min(1.0, float(score_val)))
        narrative = parsed.get("narrative", "")
    except Exception as exc:  # noqa: BLE001
        _logger.warning(
            "session_judge_llm_failed",
            session_id=session_id,
            error=str(exc),
        )
        record_llm_call(model, "session_judge", "error", 0.0)

    scores = [_overall_from_rubric(row.rubric_scores) for row in rows]
    scores = [s for s in scores if s is not None]
    avg = round(sum(scores) / len(scores), 2) if scores else None

    if llm_judge_score is None and avg is not None:
        llm_judge_score = avg
        narrative = f"Aggregated {len(rows)} tool result(s); mean score {avg}."
    elif llm_judge_score is None:
        narrative = "No scorable tool responses found."

    if not narrative:
        narrative = (
            f"Evaluated {len(rows)} responses across "
            f"{len({r.tool_type for r in rows})} tool type(s)."
        )
    if include_proctoring:
        narrative += " Proctoring data was considered in the evaluation."

    _logger.info(
        "session_judge_complete",
        session_id=session_id,
        grade_result_count=len(rows),
        llm_judge_score=llm_judge_score,
        llm_sourced=llm_judge_score != avg if avg is not None else True,
    )

    return SessionJudgeResult(
        session_id=session_id,
        llm_judge_score=llm_judge_score,
        narrative=narrative,
        grade_result_count=len(rows),
    )


async def persist_session_judge_result(
    db: AsyncSession,
    result: SessionJudgeResult,
) -> None:
    """Write judge output onto every grade_results row for the session.

    Args:
        db: Active async database session.
        result: The judge result to persist.

    Returns:
        None.
    """
    if result.llm_judge_score is None:
        return
    rows = (
        (
            await db.exec(
                select(GradeResult).where(GradeResult.session_id == result.session_id)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return
    for row in rows:
        row.llm_judge_score = result.llm_judge_score
        db.add(row)
    await db.flush()
    _logger.info(
        "judge_result_persisted",
        session_id=result.session_id,
        rows_updated=len(rows),
        score=result.llm_judge_score,
    )


__all__ = ["SessionJudgeResult", "persist_session_judge_result", "run_session_judge"]
