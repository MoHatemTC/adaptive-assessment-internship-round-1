"""Business orchestration for code challenges and submissions."""

from __future__ import annotations

import json

from fastapi import HTTPException, status
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.code import adaptation, analysis, evaluation_memory, grading, tool
from app.features.code.models import (
    CodeChallenge,
    CodeSubmission,
    SubmissionStatus,
    TestCase,
)
from app.features.code.schemas import (
    AdaptiveContract,
    AdaptiveSubmitRequest,
    AdaptiveSubmitResponse,
    ChallengeCreate,
    ChallengeListItem,
    ChallengeRead,
    RubricScoreRead,
    SubmissionCreate,
    SubmissionRead,
    TestCaseDTO,
    TestCaseRead,
)


def _test_case_to_dto(tc: TestCase) -> TestCaseDTO:
    return TestCaseDTO(
        id=str(tc.id),
        input=tc.input,
        expected_output=tc.expected_output,
        is_hidden=tc.is_hidden,
        weight=tc.weight,
    )


def _challenge_to_read(challenge: CodeChallenge, *, learner_view: bool = False) -> ChallengeRead:
    test_cases: list[TestCaseRead] = []
    for tc in challenge.test_cases:
        test_cases.append(
            TestCaseRead(
                id=tc.id or 0,
                input=tc.input,
                expected_output=None if (learner_view and tc.is_hidden) else tc.expected_output,
                is_hidden=tc.is_hidden,
                weight=tc.weight,
            )
        )
    return ChallengeRead(
        id=challenge.id or 0,
        title=challenge.title,
        description=challenge.description,
        starter_code=challenge.starter_code,
        language=challenge.language,
        time_limit_seconds=challenge.time_limit_seconds,
        test_cases=test_cases,
        created_at=challenge.created_at,
        updated_at=challenge.updated_at,
    )


def _submission_to_read(
    submission: CodeSubmission,
    *,
    scores: list[dict] | None = None,
    test_results: list | None = None,
    total_tests: int = 0,
    passed_tests: int = 0,
    hidden_tests_count: int = 0,
    error: str | None = None,
) -> SubmissionRead:
    rubric_scores = [RubricScoreRead(**s) for s in (scores or [])]
    return SubmissionRead(
        id=submission.id or 0,
        challenge_id=submission.challenge_id,
        session_id=submission.session_id,
        submitted_code=submission.submitted_code,
        status=submission.status,
        score=submission.score,
        passed=submission.passed,
        scores=rubric_scores,
        test_results=test_results or [],
        total_tests=total_tests,
        passed_tests=passed_tests,
        hidden_tests_count=hidden_tests_count,
        error=error,
        created_at=submission.created_at,
        updated_at=submission.updated_at,
    )


async def create_challenge(db: AsyncSession, payload: ChallengeCreate) -> ChallengeRead:
    challenge = CodeChallenge(
        title=payload.title,
        description=payload.description,
        starter_code=payload.starter_code,
        language=payload.language,
        time_limit_seconds=payload.time_limit_seconds,
    )
    db.add(challenge)
    await db.flush()

    for tc in payload.test_cases:
        db.add(
            TestCase(
                challenge_id=challenge.id or 0,
                input=tc.input,
                expected_output=tc.expected_output,
                is_hidden=tc.is_hidden,
                weight=tc.weight,
            )
        )

    await db.commit()
    result = await db.exec(
        select(CodeChallenge)
        .where(CodeChallenge.id == challenge.id)
        .options(selectinload(CodeChallenge.test_cases))
    )
    loaded = result.one()
    return _challenge_to_read(loaded)


async def list_challenges(db: AsyncSession) -> list[ChallengeListItem]:
    result = await db.exec(select(CodeChallenge).order_by(CodeChallenge.id))
    challenges = result.all()
    return [
        ChallengeListItem(
            id=c.id or 0,
            title=c.title,
            language=c.language,
            time_limit_seconds=c.time_limit_seconds,
            created_at=c.created_at,
        )
        for c in challenges
    ]


async def get_challenge(
    db: AsyncSession,
    challenge_id: int,
    *,
    learner_view: bool = True,
) -> ChallengeRead:
    result = await db.exec(
        select(CodeChallenge)
        .where(CodeChallenge.id == challenge_id)
        .options(selectinload(CodeChallenge.test_cases))
    )
    challenge = result.first()
    if challenge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found")
    return _challenge_to_read(challenge, learner_view=learner_view)


async def get_submission(db: AsyncSession, submission_id: int) -> SubmissionRead:
    result = await db.exec(select(CodeSubmission).where(CodeSubmission.id == submission_id))
    submission = result.first()
    if submission is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    metadata: dict = {}
    if submission.grading_metadata:
        metadata = json.loads(submission.grading_metadata)

    return _submission_to_read(
        submission,
        scores=metadata.get("scores"),
        test_results=metadata.get("test_results"),
        total_tests=metadata.get("total_tests", 0),
        passed_tests=metadata.get("passed_tests", 0),
        hidden_tests_count=metadata.get("hidden_tests_count", 0),
        error=metadata.get("error"),
    )


async def submit_code(db: AsyncSession, payload: SubmissionCreate) -> SubmissionRead:
    result = await db.exec(
        select(CodeChallenge)
        .where(CodeChallenge.id == payload.challenge_id)
        .options(selectinload(CodeChallenge.test_cases))
    )
    challenge = result.first()
    if challenge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found")
    if not challenge.test_cases:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Challenge has no test cases",
        )

    submission = CodeSubmission(
        challenge_id=payload.challenge_id,
        session_id=payload.session_id,
        submitted_code=payload.submitted_code,
        status=SubmissionStatus.RUNNING,
    )
    db.add(submission)
    await db.flush()

    test_case_dtos = [_test_case_to_dto(tc) for tc in challenge.test_cases]
    outcome, results, sandbox_error = await tool.execute_submission(
        payload.submitted_code,
        test_case_dtos,
        language=challenge.language,
        timeout_seconds=challenge.time_limit_seconds,
    )

    overall_score = tool.compute_weighted_score(test_case_dtos, results)
    passed = overall_score >= tool.PASS_THRESHOLD
    scores = tool.build_rubric_scores(results, overall_score)
    visible_results = tool.filter_visible_results(test_case_dtos, results)

    metadata = {
        "scores": scores,
        "test_results": [r.model_dump() for r in visible_results],
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
    await db.commit()
    await db.refresh(submission)

    return _submission_to_read(
        submission,
        scores=scores,
        test_results=visible_results,
        total_tests=metadata["total_tests"],
        passed_tests=metadata["passed_tests"],
        hidden_tests_count=metadata["hidden_tests_count"],
        error=metadata.get("error"),
    )


async def run_adaptive_loop(
    db: AsyncSession,
    submission_id: int,
    session_id: str,
    assessment_id: str,
    question_index: int,
    difficulty: str,
) -> AdaptiveContract:
    """Run the four adaptive-loop layers sequentially for one submission.

    Grades the submission (Layer 1), extracts an evidence memory card
    (Layer 2), aggregates skill-dimension scores (Layer 3) and computes the
    adaptive contract for the next question (Layer 4). Layers 1–3 persist rows;
    Layer 4 only reads. The caller is responsible for committing.

    Args:
        db: Active async database session.
        submission_id: PK of the graded ``code_submissions`` row.
        session_id: Platform assessment session UUID.
        assessment_id: Parent assessment identifier.
        question_index: Zero-based position in the assessment blueprint.
        difficulty: Difficulty tier of the answered question.

    Returns:
        The :class:`AdaptiveContract` for the next question.
    """
    grade = await grading.grade_submission(db, submission_id, session_id, question_index)
    await evaluation_memory.extract_memory_card(
        db, session_id, question_index, grade.id, difficulty
    )
    await analysis.analyse_session(db, session_id, question_index)
    return await adaptation.compute_adaptive_contract(db, session_id, assessment_id)


async def adaptive_submit(
    db: AsyncSession, payload: AdaptiveSubmitRequest
) -> AdaptiveSubmitResponse:
    """Accept a submission, run the adaptive loop, and return the next contract.

    Persists the submission (with sandbox grading), runs the four-layer loop,
    commits, and returns only learner-safe data plus the adaptive contract.

    Args:
        db: Active async database session.
        payload: The adaptive submit request.

    Returns:
        An :class:`AdaptiveSubmitResponse` with the submission outcome and the
        adaptive contract for the next question.
    """
    submission = await submit_code(
        db,
        SubmissionCreate(
            challenge_id=payload.challenge_id,
            session_id=payload.session_id,
            submitted_code=payload.submitted_code,
        ),
    )

    contract = await run_adaptive_loop(
        db,
        submission_id=submission.id,
        session_id=payload.session_id,
        assessment_id=payload.assessment_id,
        question_index=payload.question_index,
        difficulty=payload.difficulty,
    )
    await db.commit()

    return AdaptiveSubmitResponse(
        submission_id=submission.id,
        passed=submission.passed,
        score=submission.score,
        contract=contract,
    )
