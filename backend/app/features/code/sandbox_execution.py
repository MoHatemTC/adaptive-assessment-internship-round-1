"""E2B sandbox execution and submission persistence."""

from __future__ import annotations

import json

from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.code import tool
from app.features.code.models import CodeChallenge, CodeSubmission, SubmissionStatus, TestCase
from app.features.code.schemas import TestCaseDTO


def _test_case_to_dto(tc: TestCase) -> TestCaseDTO:
    return TestCaseDTO(
        id=str(tc.id),
        input=tc.input,
        expected_output=tc.expected_output,
        is_hidden=tc.is_hidden,
        weight=tc.weight,
    )


async def run_sandbox_for_submission(
    db: AsyncSession,
    *,
    submission: CodeSubmission,
    challenge: CodeChallenge,
    submitted_code: str,
    commit: bool = True,
) -> CodeSubmission:
    """Execute learner code in E2B (or local fallback) and persist grading metadata."""
    test_case_dtos = [_test_case_to_dto(tc) for tc in challenge.test_cases]
    outcome, results, sandbox_error = await tool.execute_submission(
        submitted_code,
        test_case_dtos,
        language=challenge.language,
        timeout_seconds=challenge.time_limit_seconds,
    )

    overall_score = tool.compute_weighted_score(test_case_dtos, results)
    passed = overall_score >= tool.PASS_THRESHOLD
    scores = tool.build_rubric_scores(results, overall_score)
    visible_results = tool.filter_visible_results(test_case_dtos, results)

    metadata: dict[str, object] = {
        "scores": scores,
        "test_results": [r.model_dump() for r in visible_results],
        "all_test_results": [r.model_dump() for r in results],
        "total_tests": len(test_case_dtos),
        "passed_tests": sum(1 for r in results if r.passed),
        "hidden_tests_count": sum(1 for tc in test_case_dtos if tc.is_hidden),
    }
    if sandbox_error and outcome.value != "success":
        metadata["error"] = sandbox_error

    submission.status = SubmissionStatus.COMPLETED
    submission.score = overall_score
    submission.passed = passed
    submission.grading_metadata = json.dumps(metadata)
    db.add(submission)
    if commit:
        await db.commit()
        await db.refresh(submission)
    return submission


async def mark_submission_failed(
    db: AsyncSession,
    *,
    submission: CodeSubmission,
    error: str,
    commit: bool = True,
) -> CodeSubmission:
    """Persist a terminal failure for a sandbox run."""
    submission.status = SubmissionStatus.FAILED
    submission.grading_metadata = json.dumps({"error": error})
    db.add(submission)
    if commit:
        await db.commit()
        await db.refresh(submission)
    return submission


__all__ = ["mark_submission_failed", "run_sandbox_for_submission"]
