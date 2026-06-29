"""MCQ evaluation layer — silent objective grading and memory extraction.

Layer 1 of the MCQ adaptive loop. For one submitted answer it:

1. Loads the :class:`~app.features.mcq.models.MCQResponse` and its question.
2. Grades objectively by comparing the selected option label against the
   question's stored ``correct_option`` (same normalization as the ``/mcq/submit``
   path, so case/whitespace never cause a false mismatch).
3. Persists ``score`` (0.0/1.0) and ``grading_feedback`` on the response, and
   guarantees the question carries a ``dimension`` — these are exactly the
   columns the shared adaptation agent's ``_fetch_mcq_answers`` reads.
4. Extracts a memory card via :func:`app.agent.memory_agent.run_memory_agent`.

Grading is silent by law: nothing here — score, correctness, feedback, the
memory card, or the dimension — is ever returned to the learner. The caller
(``loop.py`` / the ``/answer`` endpoint) is responsible for enforcing that.
"""

from __future__ import annotations

import json
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agent.memory_agent import run_memory_agent
from app.core.logging import get_logger
from app.features.mcq.models import (
    MCQOption,
    MCQQuestion,
    MCQResponse,
    SkillDimension,
)
from app.features.mcq.service import normalize_option_id
from app.shared.grading_persist import persist_grade_result, rubric_from_objective_score

logger = get_logger(__name__)

#: Maps MCQ difficulty labels onto the platform ``DifficultyLevel`` vocabulary
#: that ``run_memory_agent`` / ``MemoryCardCreate`` require.
DIFFICULTY_MAP: dict[str, str] = {
    "easy": "beginner",
    "medium": "intermediate",
    "hard": "advanced",
    "beginner": "beginner",
    "intermediate": "intermediate",
    "advanced": "advanced",
}

#: Fallback dimension when a question has none, so ``_fetch_mcq_answers`` never
#: crashes reading ``question.dimension.value``.
_DEFAULT_DIMENSION: SkillDimension = SkillDimension.thinking


async def evaluate_mcq_answer(
    session_id: str,
    question_index: int,
    mcq_response_id: int,
    db: AsyncSession,
    *,
    skip_memory: bool = False,
) -> dict[str, Any]:
    """Grade one MCQ answer silently and extract a memory card.

    Loads the response and its question, grades objectively, persists the grade
    so the shared adaptation agent can read it, and runs the memory agent. The
    returned payload is for internal callers only and must never reach the
    learner.

    Args:
        session_id: Platform assessment session UUID (String 36).
        question_index: Zero-based index of this question in the session.
        mcq_response_id: Primary key of the :class:`MCQResponse` row to grade.
        db: Active async database session.

    Returns:
        A dict with keys ``memory_card`` (a ``MemoryCardRead`` or ``None``) and
        ``memory_summary`` (str). Never includes score, correctness, or any
        grading detail.

    Raises:
        ValueError: If the response or its question cannot be found.
    """
    # 1. Load the response to grade.
    response_result = await db.exec(
        select(MCQResponse).where(MCQResponse.id == mcq_response_id)
    )
    mcq_response = response_result.first()
    if mcq_response is None:
        raise ValueError(f"MCQResponse not found: {mcq_response_id}")

    # 2. Load its question.
    question_result = await db.exec(
        select(MCQQuestion).where(MCQQuestion.id == mcq_response.question_id)
    )
    question = question_result.first()
    if question is None:
        raise ValueError(f"MCQQuestion not found: {mcq_response.question_id}")

    # 3. Load the options to resolve the selected/correct option text.
    options_result = await db.exec(
        select(MCQOption).where(MCQOption.question_id == question.id)
    )
    options = options_result.all()

    # 4. Grade objectively by normalized option-label match.
    normalized_selected = normalize_option_id(mcq_response.selected_option)
    normalized_correct = normalize_option_id(question.correct_option)
    passed = normalized_selected == normalized_correct
    score = 1.0 if passed else 0.0

    selected_option = next(
        (o for o in options if normalize_option_id(o.label) == normalized_selected),
        None,
    )
    correct_option = next(
        (o for o in options if normalize_option_id(o.label) == normalized_correct),
        None,
    )
    learner_response_text = (
        selected_option.text if selected_option else mcq_response.selected_option
    )

    # 5. Guarantee the question has a dimension; the shared adaptation agent
    #    reads ``question.dimension.value`` and must never see ``None``.
    dimension = question.dimension or _DEFAULT_DIMENSION
    if question.dimension is None:
        question.dimension = dimension
    dimension_value = dimension.value

    # 6. Build internal grading feedback (server-side only).
    grading_feedback = (
        "Correct answer selected."
        if passed
        else (
            "Incorrect. Correct answer was: "
            f"{correct_option.text if correct_option else question.correct_option}"
        )
    )

    rubric_scores = {
        "accuracy": score,
        "dimension": dimension_value,
        "is_correct": passed,
    }

    # 7. Persist the silent grade — what ``_fetch_mcq_answers`` reads.
    mcq_response.score = score
    mcq_response.grading_feedback = grading_feedback
    await persist_grade_result(
        db,
        session_id=session_id,
        tool_type="mcq",
        tool_session_id=mcq_response_id,
        question_index=question_index,
        rubric_scores=rubric_from_objective_score(
            score=score,
            dimension=dimension_value,
            feedback=grading_feedback,
        ),
    )
    await db.commit()

    logger.info(
        "mcq_evaluated",
        session_id=session_id,
        question_index=question_index,
        passed=passed,
        dimension=dimension_value,
    )

    if skip_memory:
        return {"memory_card": None, "memory_summary": ""}

    # Reuse the response/question/options already loaded above — no re-query.
    return await _run_mcq_memory_agent(
        session_id=session_id,
        question_index=question_index,
        mcq_response=mcq_response,
        question=question,
        options=options,
        db=db,
    )


async def _run_mcq_memory_agent(
    *,
    session_id: str,
    question_index: int,
    mcq_response: MCQResponse,
    question: MCQQuestion,
    options: list[MCQOption],
    db: AsyncSession,
) -> dict[str, Any]:
    """Run the memory agent from already-loaded MCQ objects (no DB round-trips)."""
    normalized_selected = normalize_option_id(mcq_response.selected_option)
    selected_option = next(
        (o for o in options if normalize_option_id(o.label) == normalized_selected),
        None,
    )
    learner_response_text = (
        selected_option.text if selected_option else mcq_response.selected_option
    )
    passed = (mcq_response.score or 0.0) >= 0.5
    dimension = question.dimension or _DEFAULT_DIMENSION
    dimension_value = dimension.value
    rubric_scores = {
        "accuracy": mcq_response.score or 0.0,
        "dimension": dimension_value,
        "is_correct": passed,
    }
    difficulty_for_memory = DIFFICULTY_MAP.get(
        question.difficulty or "medium", "beginner"
    )
    memory_card, memory_summary = await run_memory_agent(
        session_id=session_id,
        tool_type="mcq",
        question_index=question_index,
        question_text=question.question_text,
        learner_response=learner_response_text,
        rubric_scores_json=json.dumps(rubric_scores),
        passed=passed,
        difficulty=difficulty_for_memory,
    )

    return {
        "memory_card": memory_card,
        "memory_summary": memory_summary,
    }


async def extract_mcq_memory_for_response(
    session_id: str,
    question_index: int,
    mcq_response_id: int,
    db: AsyncSession,
) -> dict[str, Any]:
    """Run the memory agent for an already-graded MCQ response (standalone load)."""
    response_result = await db.exec(
        select(MCQResponse).where(MCQResponse.id == mcq_response_id)
    )
    mcq_response = response_result.first()
    if mcq_response is None:
        raise ValueError(f"MCQResponse not found: {mcq_response_id}")

    question_result = await db.exec(
        select(MCQQuestion).where(MCQQuestion.id == mcq_response.question_id)
    )
    question = question_result.first()
    if question is None:
        raise ValueError(f"MCQQuestion not found: {mcq_response.question_id}")

    options_result = await db.exec(
        select(MCQOption).where(MCQOption.question_id == question.id)
    )
    options = options_result.all()

    return await _run_mcq_memory_agent(
        session_id=session_id,
        question_index=question_index,
        mcq_response=mcq_response,
        question=question,
        options=list(options),
        db=db,
    )
