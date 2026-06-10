from typing import Any, Dict, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.mcq.models import MCQOption, MCQQuestion, MCQResponse


def normalize_answer(answer: str) -> str:
    """
    Normalize MCQ answer labels before comparison.

    Example:
    " c " -> "C"
    """
    return answer.strip().upper()


def grade_answer(correct_option: str, selected_option: str) -> Dict[str, Any]:
    """
    Grade an MCQ answer objectively.

    Returns:
    - is_correct
    - score
    """
    normalized_correct = normalize_answer(correct_option)
    normalized_selected = normalize_answer(selected_option)

    is_correct = normalized_correct == normalized_selected

    return {
        "is_correct": is_correct,
        "score": 1 if is_correct else 0,
    }


async def seed_sample_question(db: AsyncSession) -> None:
    """
    Seed one sample MCQ question if it does not already exist.

    This keeps Sprint 1 functional without requiring LLM question generation.
    """
    result = await db.exec(
        select(MCQQuestion).where(MCQQuestion.id == 1)
    )
    existing_question = result.first()

    if existing_question:
        return

    question = MCQQuestion(
        id=1,
        question_text="What is the output of print(2 + 3)?",
        difficulty="easy",
        correct_option="C",
    )

    db.add(question)

    # Important: flush the question first so PostgreSQL sees question_id=1
    # before inserting options that reference it.
    await db.flush()

    options = [
        MCQOption(question_id=1, label="A", text="2"),
        MCQOption(question_id=1, label="B", text="3"),
        MCQOption(question_id=1, label="C", text="5"),
        MCQOption(question_id=1, label="D", text="23"),
    ]

    for option in options:
        db.add(option)

    await db.flush()


async def build_sample_question(
    db: AsyncSession,
    topic: str = "Python basics",
    difficulty: str = "easy",
    question_count: int = 1,
) -> Dict[str, Any]:
    """
    Return an MCQ question from PostgreSQL.

    The topic and question_count parameters are kept for the LangChain/API
    contract, even though Sprint 1 currently serves a seeded sample question.
    """
    await seed_sample_question(db)

    question_result = await db.exec(
        select(MCQQuestion).where(MCQQuestion.id == 1)
    )
    question = question_result.first()

    if question is None:
        raise ValueError("MCQ question was not found in database.")

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
            {
                "label": option.label,
                "text": option.text,
            }
            for option in options
        ],
    }


async def get_correct_option(
    db: AsyncSession,
    question_id: int,
) -> str:
    """
    Return the correct answer for a question from PostgreSQL.
    """
    await seed_sample_question(db)

    result = await db.exec(
        select(MCQQuestion).where(MCQQuestion.id == question_id)
    )
    question = result.first()

    if question is None:
        return "C"

    return question.correct_option


async def build_submit_response(
    db: AsyncSession,
    question_id: int,
    selected_option: str,
    correct_option: Optional[str] = None,
    learner_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Submit, silently grade, and persist an MCQ response in PostgreSQL.
    """
    # Ensure the sample question exists before saving a response.
    await seed_sample_question(db)

    normalized_selected = normalize_answer(selected_option)

    correct = correct_option or await get_correct_option(
        db=db,
        question_id=question_id,
    )

    grading_result = grade_answer(
        correct_option=correct,
        selected_option=normalized_selected,
    )

    response = MCQResponse(
        question_id=question_id,
        learner_id=learner_id,
        selected_option=normalized_selected,
        is_correct=grading_result["is_correct"],
        score=grading_result["score"],
    )

    db.add(response)
    await db.flush()

    return {
        "question_id": response.question_id,
        "selected_option": response.selected_option,
        "is_correct": response.is_correct,
        "score": response.score,
    }