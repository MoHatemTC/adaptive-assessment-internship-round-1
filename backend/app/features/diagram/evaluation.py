"""Diagram evaluation layer — memory card extraction after grading.

Grading is already done in service.submit_response. This layer loads the
persisted response and runs the memory agent to extract one evidence card.
Nothing here is returned to the learner.
"""
from __future__ import annotations

import json
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.agent.memory_agent import run_memory_agent
from app.core.logging import get_logger
from app.features.diagram.models import (
    DiagramQuestion,
    DiagramResponse,
    DiagramSkillDimension,
)

logger = get_logger(__name__)

DIFFICULTY_MAP: dict[str, str] = {
    "easy": "beginner",
    "medium": "intermediate",
    "hard": "advanced",
    "beginner": "beginner",
    "intermediate": "intermediate",
    "advanced": "advanced",
}
_DEFAULT_DIMENSION = DiagramSkillDimension.thinking


async def evaluate_diagram_answer(
    session_id: str,
    question_index: int,
    diagram_response_id: int,
    db: AsyncSession,
) -> dict[str, Any]:
    result = await db.exec(
        select(DiagramResponse).where(DiagramResponse.id == diagram_response_id)
    )
    response = result.first()
    if response is None:
        raise ValueError(f"DiagramResponse not found: {diagram_response_id}")

    q_result = await db.exec(
        select(DiagramQuestion).where(DiagramQuestion.id == response.question_id)
    )
    question = q_result.first()
    if question is None:
        raise ValueError(f"DiagramQuestion not found: {response.question_id}")

    dimension = question.dimension or _DEFAULT_DIMENSION
    if question.dimension is None:
        question.dimension = dimension
    dimension_value = dimension.value

    score = response.score or 0.0
    passed = score >= 0.5
    rubric_scores = {"score": score, "dimension": dimension_value, "passed": passed}

    difficulty_for_memory = DIFFICULTY_MAP.get(question.difficulty or "easy", "beginner")

    memory_card, memory_summary = await run_memory_agent(
        session_id=session_id,
        tool_type="diagram",
        question_index=question_index,
        question_text=question.prompt,
        learner_response=response.answer_text,
        rubric_scores_json=json.dumps(rubric_scores),
        passed=passed,
        difficulty=difficulty_for_memory,
    )

    logger.info(
        "diagram_evaluated",
        session_id=session_id,
        question_index=question_index,
        passed=passed,
        dimension=dimension_value,
    )

    return {"memory_card": memory_card, "memory_summary": memory_summary}
