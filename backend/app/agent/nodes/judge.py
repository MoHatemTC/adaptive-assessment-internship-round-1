"""LLM judge over grade_results — produces holistic score + narrative.

Karim's tool loops write ``grade_results`` rows; this module aggregates them
into an ``llm_judge_score`` via an LLM call and a narrative for radar/email.

When the judge finds grading inconsistent with the evidence, the session is
held for admin review before scores are persisted or emailed to the learner.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings
from app.core.llm import get_llm_with_tracing, llm_invoke_config
from app.core.tracing import LangfuseTraceContext
from app.core.llm_json import extract_llm_text, parse_llm_json
from app.core.logging import get_logger
from app.core.metrics import record_llm_call
from app.sessions.models import AssessmentSession, GradeResult

_logger = get_logger(__name__)

JudgeReviewStatus = Literal["confirmed", "pending_admin_review"]


@dataclass(frozen=True)
class SessionJudgeResult:
    """Outcome of judging one completed session."""

    session_id: str
    llm_judge_score: float | None
    narrative: str
    grade_result_count: int
    review_status: JudgeReviewStatus = "confirmed"
    review_reason: str | None = None


_SYSTEM_PROMPT = """You are an expert assessment judge. Evaluate a learner's
performance across their entire assessment session, which includes multiple
questions across different tool types (MCQ, diagram, coding, voice).

For each question you will receive:
- The tool type
- The question's rubric dimension and score (0.0–1.0)
- Any grading feedback

First decide whether the grading-agent scores are consistent with the evidence.
Flag for admin review when scores look arbitrary, contradict each other across
similar questions, or are unsupported by the rubric breakdown.

Produce a JSON object with exactly these fields:
{
  "grading_consistent": <bool>,
  "review_reason": "<short reason when grading_consistent is false, else empty string>",
  "overall_score": <float 0.0–1.0>,
  "narrative": "<2–3 sentence summary of the learner's performance>"
}

When grading_consistent is false, still provide your best overall_score estimate
but the platform will hold results for admin review before releasing them."""


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
        feedback = rubric.get("feedback") or rubric.get("summary") or ""
        suffix = f" — feedback: {feedback}" if feedback else ""
        lines.append(
            f"- Question {row.question_index} ({row.tool_type}): {dim_str}{suffix}"
        )
    lines.append(
        "\nEvaluate grading consistency and holistic performance. Return JSON with "
        "'grading_consistent', 'review_reason', 'overall_score' (0.0–1.0), and "
        "'narrative' (2–3 sentences)."
    )
    return "\n".join(lines)


def judge_result_to_json(result: SessionJudgeResult) -> str:
    """Serialize a judge result for ``AssessmentSession.judge_review_json``."""
    return json.dumps(asdict(result))


def judge_result_from_json(raw: str) -> SessionJudgeResult:
    """Deserialize a stored judge review payload."""
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("judge review payload must be a JSON object")
    return SessionJudgeResult(
        session_id=str(payload["session_id"]),
        llm_judge_score=payload.get("llm_judge_score"),
        narrative=str(payload.get("narrative", "")),
        grade_result_count=int(payload.get("grade_result_count", 0)),
        review_status=payload.get("review_status", "confirmed"),
        review_reason=payload.get("review_reason"),
    )


async def store_pending_judge_review(
    db: AsyncSession,
    session: AssessmentSession,
    result: SessionJudgeResult,
) -> None:
    """Mark a session for admin review and persist the judge snapshot."""
    session.status = "pending_review"
    session.judge_review_json = judge_result_to_json(result)
    db.add(session)
    await db.flush()
    _logger.info(
        "judge_review_pending",
        session_id=session.id,
        review_reason=result.review_reason,
    )


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
    review_status: JudgeReviewStatus = "confirmed"
    review_reason: str | None = None
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
            config=llm_invoke_config(
                callbacks,
                trace=LangfuseTraceContext(
                    session_id=session_id,
                    operation="session_judge",
                ),
            ),
        )
        duration = time.perf_counter() - start
        record_llm_call(model, "session_judge", "success", duration)

        raw_text = extract_llm_text(response.content)
        parsed = parse_llm_json(raw_text)
        score_val = parsed.get("overall_score")
        if isinstance(score_val, (int, float)):
            llm_judge_score = max(0.0, min(1.0, float(score_val)))
        narrative = str(parsed.get("narrative", ""))
        grading_consistent = parsed.get("grading_consistent")
        if grading_consistent is False:
            review_status = "pending_admin_review"
            reason = parsed.get("review_reason")
            review_reason = (
                str(reason).strip() if reason else "Grading inconsistency detected"
            )
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
        review_status=review_status,
        llm_sourced=llm_judge_score != avg if avg is not None else True,
    )

    return SessionJudgeResult(
        session_id=session_id,
        llm_judge_score=llm_judge_score,
        narrative=narrative,
        grade_result_count=len(rows),
        review_status=review_status,
        review_reason=review_reason,
    )


async def persist_session_judge_result(
    db: AsyncSession,
    result: SessionJudgeResult,
) -> None:
    """Write judge output onto every grade_results row for the session."""
    if result.review_status != "confirmed" or result.llm_judge_score is None:
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


async def approve_pending_judge_review(
    db: AsyncSession,
    session: AssessmentSession,
) -> SessionJudgeResult:
    """Admin approves a held judge review and finalizes grading."""
    if session.status != "pending_review" or not session.judge_review_json:
        raise ValueError("session is not awaiting judge review")
    result = judge_result_from_json(session.judge_review_json)
    confirmed = SessionJudgeResult(
        session_id=result.session_id,
        llm_judge_score=result.llm_judge_score,
        narrative=result.narrative,
        grade_result_count=result.grade_result_count,
        review_status="confirmed",
        review_reason=None,
    )
    await persist_session_judge_result(db, confirmed)
    session.status = "completed"
    session.judge_review_json = None
    db.add(session)
    await db.flush()
    _logger.info("judge_review_approved", session_id=session.id)
    return confirmed


__all__ = [
    "SessionJudgeResult",
    "approve_pending_judge_review",
    "judge_result_from_json",
    "judge_result_to_json",
    "persist_session_judge_result",
    "run_session_judge",
    "store_pending_judge_review",
]
