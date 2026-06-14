"""Shared E2B + LLM grading pipeline for session and adaptive submits."""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlmodel.ext.asyncio.session import AsyncSession

from app.evaluation import evaluate_code_submission, evaluation_to_rubric_scores
from app.evaluation.schemas import CodeEvaluationContext, DimensionScores, EvaluationResult
from app.features.code import tool
from app.features.code.models import CodeChallenge, CodeSubmission, SubmissionStatus
from app.features.code.schemas import ExecutionOutcome, RubricScoreRead, TestCaseDTO, TestCaseResult
from app.features.code.service import _performance_ratio, _test_case_to_dto


@dataclass
class GradingOutcome:
    outcome: ExecutionOutcome
    results: list[TestCaseResult]
    sandbox_error: str | None
    pass_rate: float
    passed_count: int
    total_tests: int
    visible_results: list[TestCaseResult]
    evaluation: EvaluationResult
    scores: list[RubricScoreRead]
    passed: bool
    normalized_score: float
    metadata: dict


def dimension_signals_from_evaluation(evaluation: EvaluationResult) -> dict[str, float]:
    dims: DimensionScores = evaluation.dimension_scores
    return {
        "correctness": dims.correctness,
        "completeness": dims.completeness,
        "code_quality": dims.code_quality,
        "performance": dims.performance,
        "creativity": dims.creativity,
        "documentation": dims.documentation,
    }


async def grade_submission_in_sandbox(
    *,
    challenge: CodeChallenge,
    submitted_code: str,
    session_id: str,
    test_case_dtos: list[TestCaseDTO],
    e2b_template: str | None = None,
    kill_existing_sandbox_id: str | None = None,
) -> GradingOutcome:
    """Run full hidden tests + LLM rubric; does not persist submission."""
    if kill_existing_sandbox_id:
        await tool.kill_sandbox(kill_existing_sandbox_id)

    outcome, results, sandbox_error, _ = await tool.execute_submission(
        submitted_code,
        test_case_dtos,
        language=challenge.language,
        timeout_seconds=challenge.time_limit_seconds,
        keep_sandbox=False,
        include_hidden=True,
        template=e2b_template,
    )

    overall_score = tool.compute_weighted_score(test_case_dtos, results)
    passed_count = sum(1 for r in results if r.passed)
    visible_results = tool.filter_visible_results(test_case_dtos, results)

    eval_ctx = CodeEvaluationContext(
        challenge_id=challenge.id or 0,
        title=challenge.title,
        description=challenge.description,
        submitted_code=submitted_code,
        language=challenge.language,
        correctness_ratio=overall_score,
        performance_ratio=_performance_ratio(results),
        passed_tests=passed_count,
        total_tests=len(test_case_dtos),
        execution_error=sandbox_error,
    )
    evaluation = await evaluate_code_submission(eval_ctx)
    scores = evaluation_to_rubric_scores(evaluation)
    passed = evaluation.status == "Passed" and outcome == ExecutionOutcome.SUCCESS
    normalized_score = round(evaluation.score / 100.0, 3)

    metadata = {
        "scores": scores,
        "test_results": [r.model_dump() for r in visible_results],
        "total_tests": len(test_case_dtos),
        "passed_tests": passed_count,
        "hidden_tests_count": sum(1 for tc in test_case_dtos if tc.is_hidden),
        "evaluation": {
            "evaluation_score": evaluation.score,
            "evaluation_status": evaluation.status,
            "breakdown": evaluation.breakdown.model_dump(),
            "strengths": evaluation.strengths,
            "weaknesses": evaluation.weaknesses,
            "recommendations": evaluation.recommendations,
            "next_difficulty": evaluation.next_difficulty,
            "feedback_summary": evaluation.feedback_summary,
        },
    }
    if sandbox_error and outcome != ExecutionOutcome.SUCCESS:
        metadata["error"] = sandbox_error

    return GradingOutcome(
        outcome=outcome,
        results=results,
        sandbox_error=sandbox_error,
        pass_rate=overall_score,
        passed_count=passed_count,
        total_tests=len(test_case_dtos),
        visible_results=visible_results,
        evaluation=evaluation,
        scores=scores,
        passed=passed,
        normalized_score=normalized_score,
        metadata=metadata,
    )


async def persist_graded_submission(
    db: AsyncSession,
    *,
    challenge_id: int,
    session_id: str,
    submitted_code: str,
    grading: GradingOutcome,
) -> CodeSubmission:
    submission = CodeSubmission(
        challenge_id=challenge_id,
        session_id=session_id,
        submitted_code=submitted_code,
        status=SubmissionStatus.RUNNING,
    )
    db.add(submission)
    await db.flush()

    submission.status = (
        SubmissionStatus.COMPLETED
        if grading.outcome == ExecutionOutcome.SUCCESS
        else SubmissionStatus.FAILED
    )
    submission.score = grading.normalized_score
    submission.passed = grading.passed
    submission.grading_metadata = json.dumps(grading.metadata)
    db.add(submission)
    await db.flush()
    return submission
