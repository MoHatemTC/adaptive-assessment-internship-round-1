"""Layer 2 — E2B + rubric evaluation persisted as silent memory cards."""

from __future__ import annotations

import json

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.code.adaptive_schemas import CodeToolInput, CodeToolOutput
from app.features.code.grading import (
    dimension_signals_from_evaluation,
    grade_submission_in_sandbox,
    persist_graded_submission,
)
from app.features.code.models import CodeMemoryCard
from app.features.code.service import (
    _load_attempt_challenge,
    _load_session_context,
    _performance_ratio,
    _test_case_to_dto,
)


def _challenge_meta(snapshot: dict, challenge_id: int) -> dict:
    for item in snapshot.get("challenges", []):
        if item.get("challenge_id") == challenge_id:
            return item
    return {}


async def evaluate_turn_and_persist_card(
    db: AsyncSession,
    *,
    code_session_id: str,
    challenge_id: int,
    submitted_code: str,
    platform_session_id: str | None = None,
) -> tuple[CodeToolOutput, CodeMemoryCard]:
    """Grade submission, persist submission + memory card; return silent tool output."""
    assessment, attempts, snapshot = await _load_session_context(db, code_session_id)
    attempt = next((a for a in attempts if a.challenge_id == challenge_id), None)
    if attempt is None:
        raise ValueError(f"Challenge {challenge_id} not in session {code_session_id}")

    challenge = await _load_attempt_challenge(db, attempt)
    platform = snapshot.get("platform_config", {})
    e2b_template = platform.get("challenge", {}).get("e2b_template")
    test_case_dtos = [_test_case_to_dto(tc) for tc in challenge.test_cases]

    grading = await grade_submission_in_sandbox(
        challenge=challenge,
        submitted_code=submitted_code,
        session_id=code_session_id,
        test_case_dtos=test_case_dtos,
        e2b_template=e2b_template,
        kill_existing_sandbox_id=attempt.e2b_sandbox_id,
    )
    attempt.e2b_sandbox_id = None

    submission = await persist_graded_submission(
        db,
        challenge_id=challenge_id,
        session_id=code_session_id,
        submitted_code=submitted_code,
        grading=grading,
    )

    meta = _challenge_meta(snapshot, challenge_id)
    dimension_signals = dimension_signals_from_evaluation(grading.evaluation)
    rubric_score = round(grading.evaluation.score / 100.0, 3)

    card = CodeMemoryCard(
        platform_session_id=platform_session_id,
        code_session_id=code_session_id,
        challenge_id=challenge_id,
        problem_type=meta.get("category", "general"),
        difficulty=meta.get("difficulty", "intermediate"),
        language=challenge.language,
        pass_rate=grading.pass_rate,
        efficiency=_performance_ratio(grading.results),
        rubric_score=rubric_score,
        dimension_signals_json=json.dumps(dimension_signals),
        passed=grading.passed,
        test_results_json=json.dumps([r.model_dump() for r in grading.results]),
    )
    db.add(card)
    await db.flush()

    tool_output = CodeToolOutput(
        challenge_id=challenge_id,
        objective_pass_rate=grading.pass_rate,
        efficiency_score=_performance_ratio(grading.results),
        rubric_score=rubric_score,
        dimension_signals=dimension_signals,
        memory_card_id=card.id or 0,
        passed=grading.passed,
        execution_outcome=grading.outcome.value,
    )
    return tool_output, card, submission, grading, attempt, assessment, snapshot


async def load_memory_cards(
    db: AsyncSession,
    code_session_id: str,
) -> list[CodeMemoryCard]:
    result = await db.exec(
        select(CodeMemoryCard)
        .where(CodeMemoryCard.code_session_id == code_session_id)
        .order_by(CodeMemoryCard.id)
    )
    return list(result.all())


async def run_adaptive_code_turn_from_input(
    db: AsyncSession,
    tool_input: CodeToolInput,
) -> CodeToolOutput:
    """Agent entrypoint: evaluate one turn when code is supplied."""
    if tool_input.challenge_id is None or not tool_input.submitted_code:
        raise ValueError("challenge_id and submitted_code are required for evaluation")
    output, _, _, _, _, _, _ = await evaluate_turn_and_persist_card(
        db,
        code_session_id=tool_input.code_session_id,
        challenge_id=tool_input.challenge_id,
        submitted_code=tool_input.submitted_code,
        platform_session_id=tool_input.platform_session_id,
    )
    return output
