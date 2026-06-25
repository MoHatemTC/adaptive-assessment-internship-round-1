"""Diagram persistence and silent LLM grading logic."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from langchain_core.messages import HumanMessage, SystemMessage
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import llm as llm_gateway
from app.core.logging import get_logger
from app.features.diagram.models import (
    DiagramQuestion,
    DiagramResponse,
    DiagramSkillDimension,
)

_logger = get_logger(__name__)


def _extract_json_from_llm_response(content: Any) -> Dict[str, Any]:
    """Parse a JSON object out of an LLM response.

    Handles Kimi K2's list-of-blocks content shape and stray code fences.

    Args:
        content: The ``response.content`` returned by the LLM.

    Returns:
        The parsed JSON object as a dict.

    Raises:
        ValueError: If no JSON object can be located in the response.
    """
    if isinstance(content, list):
        text_parts: List[str] = []

        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type")

                if block_type == "text" and block.get("text"):
                    text_parts.append(str(block["text"]))
                elif block_type not in {"thinking", "reasoning"}:
                    possible_text = block.get("text") or block.get("content") or ""
                    if possible_text:
                        text_parts.append(str(possible_text))
            else:
                text_parts.append(str(block))

        cleaned = "\n".join(text_parts).strip()
    else:
        cleaned = str(content).strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()

    if cleaned.endswith("```"):
        cleaned = cleaned.removesuffix("```").strip()

    start_index = cleaned.find("{")
    end_index = cleaned.rfind("}")

    if start_index == -1 or end_index == -1:
        raise ValueError("LLM response does not contain a valid JSON object")

    json_text = cleaned[start_index : end_index + 1]
    return json.loads(json_text)


def _serialize_question(question: DiagramQuestion) -> dict:
    return {
        "id": question.id,
        "svg_content": question.svg_content,
        "prompt": question.prompt,
        "difficulty": question.difficulty,
        "dimension": question.dimension.value if question.dimension else None,
    }


def _coerce_dimension(dimension: Optional[str]) -> Optional[DiagramSkillDimension]:
    if not dimension:
        return None
    try:
        return DiagramSkillDimension(dimension)
    except ValueError:
        _logger.warning("diagram_unknown_dimension", dimension=dimension)
        return None


async def _get_question_or_404(db: AsyncSession, question_id: int) -> DiagramQuestion:
    result = await db.exec(select(DiagramQuestion).where(DiagramQuestion.id == question_id))
    question = result.first()
    if question is None:
        _logger.warning("diagram_question_not_found", question_id=question_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diagram question not found",
        )
    return question


async def create_question(
    db: AsyncSession,
    svg_content: str,
    prompt: str,
    correct_label: str,
    rubric: str,
    difficulty: str = "easy",
    dimension: Optional[str] = None,
) -> dict:
    question = DiagramQuestion(
        svg_content=svg_content,
        prompt=prompt,
        correct_label=correct_label,
        rubric=rubric,
        difficulty=difficulty,
        dimension=_coerce_dimension(dimension),
    )
    db.add(question)
    await db.flush()

    _logger.info(
        "diagram_question_created",
        question_id=question.id,
        difficulty=difficulty,
        dimension=dimension,
    )
    return _serialize_question(question)


async def get_question(db: AsyncSession, question_id: int) -> dict:
    question = await _get_question_or_404(db, question_id)
    return _serialize_question(question)


async def get_correct_label(db: AsyncSession, question_id: int) -> str:
    question = await _get_question_or_404(db, question_id)
    return question.correct_label


async def submit_response(
    db: AsyncSession,
    question_id: int,
    session_id: str,
    answer_text: str,
    learner_id: Optional[str] = None,
) -> dict:
    question = await _get_question_or_404(db, question_id)
    response = DiagramResponse(
        question_id=question_id,
        session_id=session_id,
        answer_text=answer_text,
        learner_id=learner_id,
        score=None,
        grading_feedback=None,
    )
    db.add(response)
    await db.flush()

    grading = await grade_answer(
        correct_label=question.correct_label,
        rubric=question.rubric,
        answer_text=answer_text,
    )
    response.score = grading["score"]
    response.grading_feedback = grading["feedback"]
    await db.flush()

    _logger.info(
        "diagram_answer_graded",
        response_id=response.id,
        session_id=session_id,
        score=response.score,
    )
    return {
        "question_id": response.question_id,
        "response_id": response.id,
        "score": response.score,
        "grading_feedback": response.grading_feedback,
    }


async def grade_answer(correct_label: str, rubric: str, answer_text: str) -> dict:
    system_prompt = f"""
You are a silent diagram assessment grader.
The learner was shown an architecture/system diagram with one component label
left blank. They must identify what that blank component is.

Correct label: {correct_label}
Grading context: {rubric}

Rules:
- Accept semantically equivalent answers (e.g. "load balancer" = "Load Balancer" = "LB").
- Accept partial matches if the core concept is correct.
- Reject answers that are clearly wrong or name a completely different component.
- Return ONLY valid JSON, no preamble, no markdown: {{"score": 1, "feedback": "string"}}
  where score is exactly 1 (correct) or 0 (wrong).
""".strip()

    try:
        llm, callbacks = llm_gateway.get_llm_with_tracing()
        response = await llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Learner's answer: {answer_text}"),
            ],
            config={"callbacks": callbacks},
        )
        parsed = _extract_json_from_llm_response(response.content)
        score = float(parsed.get("score", 0))
        if score not in {0.0, 1.0}:
            score = 0.0
        return {"score": score, "feedback": parsed.get("feedback", "")}
    except Exception as exc:  # noqa: BLE001 - grading must not break session
        _logger.error("diagram_grading_failed", error=str(exc))
        return {"score": 0.0, "feedback": "Grading unavailable"}
