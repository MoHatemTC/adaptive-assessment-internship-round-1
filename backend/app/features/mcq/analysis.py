"""MCQ analysis layer.

This module produces a lightweight MCQ ability estimate for the adaptive layer.

Sprint 2 schema alignment note:
The unified schema says shared evidence should be written to the platform
memory_cards and skill_dimension_scores tables, not to MCQ-owned tables.
Until the platform sessions/grading tables are available, this module analyzes
the latest internal grading result from the MCQ loop and returns the same
contract shape expected by the adaptation layer.
"""

from typing import Any, Dict

from sqlmodel.ext.asyncio.session import AsyncSession


def _mastery_from_score(score: int) -> str:
    """Convert the latest objective MCQ score into a simple mastery label."""
    if score >= 1:
        return "high"

    return "low"


async def analyze_mcq_session(
    db: AsyncSession,
    session_id: str,
    latest_grading_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a session analysis summary from the latest MCQ grading result."""
    _ = db

    score = int(latest_grading_result.get("score", 0))
    is_correct = bool(latest_grading_result.get("is_correct", False))
    difficulty = latest_grading_result.get("difficulty", "beginner")
    dimension = latest_grading_result.get("dimension") or "Thinking"

    mastery_level = _mastery_from_score(score)

    skill_stats = {
        dimension: {
            "total_questions": 1,
            "correct_answers": 1 if is_correct else 0,
            "accuracy": 1.0 if is_correct else 0.0,
            "mastery_level": mastery_level,
            "difficulties": {difficulty: 1},
        }
    }

    return {
        "session_id": session_id,
        "total_questions": 1,
        "correct_answers": 1 if is_correct else 0,
        "accuracy": 1.0 if is_correct else 0.0,
        "mastery_level": mastery_level,
        "difficulty_counts": {difficulty: 1},
        "skill_mastery": skill_stats,
        "weakest_skill": dimension,
    }
