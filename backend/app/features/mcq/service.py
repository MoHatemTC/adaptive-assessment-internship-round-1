"""MCQ persistence and silent grading logic.

This layer owns question creation/retrieval and objective grading. Grading is
silent: ``is_correct`` and ``score`` are computed and persisted for the LLM
judge and admin reporting, but the API layer never returns them to the learner.
Answers are compared as normalized option identifiers (stripped, lowercased) so
that case and whitespace differences never cause a false mismatch.
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
        option_id: Raw option identifier from the question key or the learner.

    Returns:
        The identifier stripped of surrounding whitespace and lowercased.

    Example:
        ``" B "`` -> ``"b"``
    """
    return option_id.strip().lower()


def grade_answer(correct_option: str, selected_option: str) -> Dict[str, Any]:
    """Grade an MCQ answer objectively by comparing normalized option IDs.

    Args:
        correct_option: The correct option identifier stored server-side.
        selected_option: The option identifier the learner submitted.

    Returns:
        A dict with ``is_correct`` (bool) and ``score`` (1 if correct else 0).
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
    """Fetch a question by id or raise a 404.

    Args:
        db: Active async database session.
        question_id: Primary key of the question to fetch.

    Returns:
        The matching :class:`~app.features.mcq.models.MCQQuestion`.

    Raises:
        HTTPException: 404 if no question matches ``question_id``.
    """
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
    difficulty: str = "easy",
) -> Dict[str, Any]:
    """Create an MCQ question with its options.

    Args:
        db: Active async database session.
        question_text: The prompt shown to the learner.
        correct_option: Identifier of the correct option (kept server-side).
        options: Option dicts, each with ``label`` and ``text`` keys.
        difficulty: Difficulty label. Defaults to ``"easy"``.

    Returns:
        The created question serialized without the correct answer.
    """
    question = MCQQuestion(
        question_text=question_text,
        difficulty=difficulty,
        correct_option=correct_option,
    )
    db.add(question)

    # Flush so the database assigns question.id before inserting its options.
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
        option_count=len(options),
    )

    return {
        "id": question.id,
        "question_text": question.question_text,
        "difficulty": question.difficulty,
        "options": [
            {"label": option["label"], "text": option["text"]}
            for option in options
        ],
    }


async def get_question(
    db: AsyncSession,
    question_id: int,
) -> Dict[str, Any]:
    """Return a question and its options without exposing the correct answer.

    Args:
        db: Active async database session.
        question_id: Primary key of the question to return.

    Returns:
        The question serialized with its options but no ``correct_option``.

    Raises:
        HTTPException: 404 if the question does not exist.
    """
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
        "options": [
            {"label": option.label, "text": option.text} for option in options
        ],
    }


async def get_correct_option(
    db: AsyncSession,
    question_id: int,
) -> str:
    """Return the correct option identifier for a question.

    Args:
        db: Active async database session.
        question_id: Primary key of the question.

    Returns:
        The stored correct option identifier.

    Raises:
        HTTPException: 404 if the question does not exist (no silent fallback).
    """
    question = await _get_question_or_404(db, question_id)
    return question.correct_option


async def build_submit_response(
    db: AsyncSession,
    question_id: int,
    selected_option: str,
    session_id: str,
    correct_option: Optional[str] = None,
    learner_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Silently grade and persist an MCQ response.

    The returned dict includes ``is_correct`` and ``score`` for internal callers
    (the LLM judge and admin reporting). The API layer must not forward those
    fields to the learner.

    Args:
        db: Active async database session.
        question_id: Primary key of the answered question.
        selected_option: The option identifier the learner submitted.
        session_id: Owning assessment session id, stored on the response.
        correct_option: Optional correct option, looked up when not supplied.
        learner_id: Optional learner identifier.

    Returns:
        A dict with ``question_id``, ``is_correct``, and ``score``.

    Raises:
        HTTPException: 404 if the question does not exist.
    """
    correct = correct_option or await get_correct_option(
        db=db,
        question_id=question_id,
    )

    normalized_selected = normalize_option_id(selected_option)

    grading_result = grade_answer(
        correct_option=correct,
        selected_option=normalized_selected,
    )

    response = MCQResponse(
        question_id=question_id,
        session_id=session_id,
        learner_id=learner_id,
        selected_option=normalized_selected,
        is_correct=grading_result["is_correct"],
        score=grading_result["score"],
    )

    db.add(response)
    await db.flush()

    # Silent grading: log server-side for the judge/reporting, never returned.
    _logger.info(
        "mcq_answer_graded",
        question_id=question_id,
        session_id=session_id,
        is_correct=grading_result["is_correct"],
    )

    return {
        "question_id": response.question_id,
        "is_correct": response.is_correct,
        "score": response.score,
    }
