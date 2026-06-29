"""Persist tool grading output to the platform ``grade_results`` table."""

from __future__ import annotations

import json
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logging import get_logger
from app.sessions.models import GradeResult
from app.shared.schemas.memory import RubricDimension, RubricScores

_logger = get_logger(__name__)


def rubric_from_objective_score(
    *,
    score: float,
    dimension: str | None = None,
    feedback: str = "",
) -> RubricScores:
    """Map a 0–1 objective score into the shared rubric schema."""
    clamped = max(0.0, min(1.0, float(score)))
    dimensions = [
        RubricDimension(
            name=dimension or "accuracy",
            score=clamped,
            feedback=feedback or ("Correct." if clamped >= 0.5 else "Incorrect."),
        )
    ]
    return RubricScores(dimensions=dimensions, overall=clamped)


async def persist_grade_result(
    db: AsyncSession,
    *,
    session_id: str,
    tool_type: str,
    tool_session_id: int,
    question_index: int,
    rubric_scores: RubricScores | dict[str, Any],
) -> int:
    """Insert one ``grade_results`` row and return its id."""
    if isinstance(rubric_scores, RubricScores):
        payload = rubric_scores.model_dump_json()
    else:
        payload = json.dumps(rubric_scores)

    row = GradeResult(
        session_id=session_id,
        tool_type=tool_type,
        tool_session_id=tool_session_id,
        question_index=question_index,
        rubric_scores=payload,
        llm_judge_score=None,
    )
    db.add(row)
    await db.flush()
    _logger.info(
        "grade_result_persisted",
        session_id=session_id,
        tool_type=tool_type,
        question_index=question_index,
        grade_result_id=row.id,
    )
    return row.id


__all__ = ["persist_grade_result", "rubric_from_objective_score"]
