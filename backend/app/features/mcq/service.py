"""MCQ persistence and silent objective grading logic.

This service follows the Masaar unified schema:

- mcq_questions stores question content, correct option, difficulty, and dimension.
- mcq_options stores answer options.
- mcq_responses stores learner submissions only.
- mcq_responses does not store scores, correctness, learner_id, or grading output.
- Objective grading is computed internally and returned to the adaptive loop,
  while platform grading tables own persisted grading output.
"""

from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logging import get_logger
from app.features.mcq.models import MCQOption, MCQQuestion, MCQResponse

_logger = get_logger(__name__)


def normalize_option_id(option_id: str) -> str:
    """Normalize an option identifier for comparison.

    Args:
        option_id: Raw option identifier from the question key or learner.

    Returns:
        The identifier stripped of surrounding whitespace and lowercased.
    """
    return option_id.strip().lower()


def grade_answer(correct_option: str, selected_option: str) -> Dict[str, Any]:
    """Grade an MCQ answer objectively by comparing normalized option labels.

    Args:
        correct_option: Correct option label stored server-side.
        selected_option: Option label submitted by the learner.

    Returns:
        Internal grading result with correctness and binary score.
    """
    is_correct = normalize_option_id(correct_option) == normalize_option_id(
        selected_option
    )

    return {
        "is_correct": is_correct,
        "score": 1 if is_correct else 0,
    }


async def _get_question_or_404(
    db: AsyncSession,
    question_id: int,
) -> MCQQuestion:
    """Fetch a question by id or raise 404."""
    result = await db.exec(
        select(MCQQuestion).where(MCQQuestion.id == question_id)
    )
    question = result.first()

    if question is None:
        _logger.warning("mcq_question_not_found", question_id=question_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="MCQ question not found",
        )

    return question


async def create_question(
    db: AsyncSession,
    question_text: str,
    correct_option: str,
    options: List[Dict[str, str]],
    difficulty: str = "beginner",
    dimension: Optional[str] = None,
) -> Dict[str, Any]:
    """Create an MCQ question with its options.

    The correct option is stored server-side only and is never returned
    in the learner-facing response.
    """
    question = MCQQuestion(
        question_text=question_text,
        difficulty=difficulty,
        correct_option=correct_option,
        dimension=dimension,
    )
    db.add(question)

    await db.flush()

    for option in options:
        db.add(
            MCQOption(
                question_id=question.id,
                label=option["label"],
                text=option["text"],
            )
        )

    await db.flush()

    _logger.info(
        "mcq_question_created",
        question_id=question.id,
        difficulty=difficulty,
        dimension=dimension,
        option_count=len(options),
    )

    return {
        "id": question.id,
        "question_text": question.question_text,
        "difficulty": question.difficulty,
        "dimension": question.dimension,
        "options": [
            {"label": option["label"], "text": option["text"]}
            for option in options
        ],
    }


async def get_question(
    db: AsyncSession,
    question_id: int,
) -> Dict[str, Any]:
    """Return a question and its options without exposing correct_option."""
    question = await _get_question_or_404(db, question_id)

    options_result = await db.exec(
        select(MCQOption)
        .where(MCQOption.question_id == question.id)
        .order_by(MCQOption.label)
    )
    options = options_result.all()

    return {
        "id": question.id,
        "question_text": question.question_text,
        "difficulty": question.difficulty,
        "dimension": question.dimension,
        "options": [
            {"label": option.label, "text": option.text} for option in options
        ],
    }


async def get_correct_option(
    db: AsyncSession,
    question_id: int,
) -> str:
    """Return the server-side correct option label for internal grading."""
    question = await _get_question_or_404(db, question_id)
    return question.correct_option


async def build_submit_response(
    db: AsyncSession,
    question_id: int,
    selected_option: str,
    session_id: str,
    question_index: int,
    correct_option: Optional[str] = None,
) -> Dict[str, Any]:
    """Silently grade and persist an MCQ response.

    mcq_responses stores only the learner submission. Correctness and score
    are computed internally for the adaptive loop, but they are not written
    to mcq_responses and must never be exposed to the learner.
    """
    question = await _get_question_or_404(db, question_id)

    correct = correct_option or question.correct_option
    selected_option_clean = selected_option.strip()

    grading_result = grade_answer(
        correct_option=correct,
        selected_option=selected_option_clean,
    )

    response = MCQResponse(
        question_id=question_id,
        session_id=session_id,
        question_index=question_index,
        selected_option=selected_option_clean,
    )

    db.add(response)
    await db.flush()

    _logger.info(
        "mcq_answer_graded_silently",
        response_id=response.id,
        question_id=question_id,
        session_id=session_id,
        question_index=question_index,
        is_correct=grading_result["is_correct"],
    )

    return {
        "response_id": response.id,
        "question_id": response.question_id,
        "session_id": response.session_id,
        "question_index": response.question_index,
        "difficulty": question.difficulty,
        "dimension": question.dimension,
        "is_correct": grading_result["is_correct"],
        "score": grading_result["score"],
    }

