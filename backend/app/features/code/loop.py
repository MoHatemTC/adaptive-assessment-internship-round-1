"""Adaptive loop orchestrator for the coding tool.

Wires layers 1–4 for one official submission: grade → memory card →
session analysis → adaptive contract for the next question.
"""

from __future__ import annotations

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logging import get_logger
from app.features.code import adaptation, analysis, evaluation, grading
from app.features.code.schemas import AdaptiveContract, LlmRubricSummary
from app.shared.schemas.memory import RubricScores

logger = get_logger(__name__)


def _rubric_dimension(rubric: RubricScores, name: str) -> tuple[float, str]:
    for dim in rubric.dimensions:
        if dim.name == name:
            return dim.score, dim.feedback
    return 0.0, ""


def _llm_rubric_summary(rubric: RubricScores) -> LlmRubricSummary:
    approach_score, approach_feedback = _rubric_dimension(rubric, "approach")
    efficiency_score, efficiency_feedback = _rubric_dimension(rubric, "efficiency")
    return LlmRubricSummary(
        approach_score=approach_score,
        approach_feedback=approach_feedback,
        efficiency_score=efficiency_score,
        efficiency_feedback=efficiency_feedback,
        overall=rubric.overall,
    )


async def run_adaptive_loop_fast(
    db: AsyncSession,
    submission_id: int,
    session_id: str,
    assessment_id: str,
    question_index: int,
    difficulty: str,
) -> tuple[AdaptiveContract, LlmRubricSummary, int]:
    """Run layers 1–4 using a sandbox-heuristic grade (no LLM wait).

    Returns:
        Contract, rubric summary, and the persisted ``grade_results`` id for
        deferred LLM upgrade.
    """
    grade = await grading.grade_submission_sandbox_only(
        db,
        submission_id,
        session_id,
        question_index,
    )
    rubric = RubricScores.model_validate_json(grade.rubric_scores)
    await evaluation.extract_memory_card(
        db, session_id, question_index, grade.id, difficulty
    )
    await analysis.analyse_session(db, session_id, question_index)
    contract = await adaptation.compute_adaptive_contract(db, session_id, assessment_id)
    return contract, _llm_rubric_summary(rubric), grade.id or 0


async def run_adaptive_loop(
    db: AsyncSession,
    submission_id: int,
    session_id: str,
    assessment_id: str,
    question_index: int,
    difficulty: str,
) -> tuple[AdaptiveContract, LlmRubricSummary]:
    """Run the four adaptive-loop layers sequentially for one submission.

    Grades the submission (Layer 1), extracts an evidence memory card
    (Layer 2), aggregates skill-dimension scores (Layer 3) and computes the
    adaptive contract for the next question (Layer 4). Layers 1–3 persist rows;
    Layer 4 only reads. The caller is responsible for committing.

    Returns:
        The next :class:`AdaptiveContract` and internal LLM rubric summary.
    """
    logger.info(
        "code_adaptive_loop_started",
        session_id=session_id,
        question_index=question_index,
    )
    grade = await grading.grade_submission(
        db,
        submission_id,
        session_id,
        question_index,
    )
    rubric = RubricScores.model_validate_json(grade.rubric_scores)
    await evaluation.extract_memory_card(
        db, session_id, question_index, grade.id, difficulty
    )
    await analysis.analyse_session(db, session_id, question_index)
    contract = await adaptation.compute_adaptive_contract(db, session_id, assessment_id)
    return contract, _llm_rubric_summary(rubric)


__all__ = ["run_adaptive_loop", "run_adaptive_loop_fast"]
