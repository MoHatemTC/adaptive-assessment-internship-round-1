"""MCQ adaptive loop service.

This module connects silent objective grading, session analysis,
adaptation, and LLM-based MCQ generation into one on-the-fly MCQ loop.

It follows the unified schema rule that mcq_responses stores learner
submissions only. Correctness and score are computed internally for the
adaptive decision but are never returned to the learner.
"""

from typing import Any, Dict, Optional

from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.mcq.adaptation import select_next_mcq_plan
from app.features.mcq.analysis import analyze_mcq_session
from app.features.mcq.llm_generation import generate_and_store_next_mcq
from app.features.mcq.service import build_submit_response


async def run_mcq_adaptive_loop(
    db: AsyncSession,
    question_id: int,
    selected_option: str,
    session_id: str,
    question_index: int,
    learner_profile: Optional[Dict[str, Any]] = None,
    admin_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run one adaptive MCQ step."""
    grading_result = await build_submit_response(
        db=db,
        question_id=question_id,
        selected_option=selected_option,
        session_id=session_id,
        question_index=question_index,
    )

    analysis = await analyze_mcq_session(
        db=db,
        session_id=session_id,
        latest_grading_result=grading_result,
    )

    next_plan = select_next_mcq_plan(
        analysis=analysis,
        learner_profile=learner_profile,
        admin_config=admin_config,
    )

    next_question = await generate_and_store_next_mcq(
        db=db,
        next_plan=next_plan,
        learner_profile=learner_profile,
        admin_config=admin_config,
    )

    return {
        "received": True,
        "question_id": question_id,
        "next_plan": next_plan,
        "next_question": next_question,
    }
