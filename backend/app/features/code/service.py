"""Business orchestration for code challenges and submissions."""

from __future__ import annotations

import json

from fastapi import HTTPException, status
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.code import (
    adaptation,
    background_grading,
    grading,
    llm_generation,
    loop,
    tool,
)
from app.features.code.languages import normalize_language
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
    GenerateChallengeRequest,
    GenerateChallengeResponse,
    RubricScoreRead,
    SubmissionCreate,
    SubmissionRead,
    TestCaseCreate,
    TestCaseDTO,
    TestCaseRead,
)
from app.sessions.models import GradeResult
from app.shared.schemas.memory import DimensionScore


def _test_case_to_dto(tc: TestCase) -> TestCaseDTO:
    return TestCaseDTO(
        id=str(tc.id),
        input=tc.input,
        expected_output=tc.expected_output,
        is_hidden=tc.is_hidden,
        weight=tc.weight,
    )


def _challenge_to_read(
    challenge: CodeChallenge,
    *,
    learner_view: bool = False,
) -> ChallengeRead:
    test_cases: list[TestCaseRead] = []
    for tc in challenge.test_cases:
        test_cases.append(
            TestCaseRead(
                id=tc.id or 0,
                input=tc.input,
                expected_output=(
                    None if (learner_view and tc.is_hidden) else tc.expected_output
                ),
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


def _starter_contract(session_id: str) -> AdaptiveContract:
    """Default contract for the first generated question in a session."""
    return AdaptiveContract(
        session_id=session_id,
        question_index=0,
        tool_type="coding",
        difficulty="beginner",
        focus_dimension=None,
        stop=False,
        memory_summary="Starting coding assessment at beginner difficulty.",
        cumulative_scores=DimensionScore(),
    )


def _learner_safe_contract(contract: AdaptiveContract) -> AdaptiveContract:
    """Strip private memory/score details before returning to the learner UI."""
    return AdaptiveContract(
        session_id=contract.session_id,
        question_index=contract.question_index,
        tool_type=contract.tool_type,
        difficulty=contract.difficulty,
        focus_dimension=contract.focus_dimension,
        stop=contract.stop,
        memory_summary="",
        cumulative_scores=DimensionScore(),
    )


async def _session_challenge_titles(db: AsyncSession, session_id: str) -> list[str]:
    rows = (
        await db.exec(
            select(CodeChallenge.title)
            .join(CodeSubmission, CodeSubmission.challenge_id == CodeChallenge.id)
            .where(CodeSubmission.session_id == session_id)
            .order_by(CodeSubmission.id)
        )
    ).all()
    return list(rows)


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


async def generate_challenge(
    db: AsyncSession,
    payload: GenerateChallengeRequest,
) -> GenerateChallengeResponse:
    """Author and persist the next challenge from an adaptive contract."""
    if payload.contract is None:
        contract = await adaptation.compute_adaptive_contract(
            db,
            payload.session_id,
            payload.assessment_id,
        )
    else:
        contract = await adaptation.compute_adaptive_contract(
            db,
            payload.session_id,
            payload.assessment_id,
        )
        if contract.question_index != payload.contract.question_index:
            contract = payload.contract

    if contract.stop:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Adaptive loop signalled stop; no further challenges.",
        )

    previous_titles = await _session_challenge_titles(db, payload.session_id)
    language = normalize_language(payload.language)
    try:
        spec = await llm_generation.generate_challenge_spec(
            contract=contract,
            assessment_id=payload.assessment_id,
            language=language,
            previous_titles=previous_titles,
        )
    except grading.LLMGradingUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    challenge = await create_challenge(
        db,
        ChallengeCreate(
            title=spec.title,
            description=spec.description,
            starter_code=spec.starter_code,
            language=language,
            time_limit_seconds=20,
            test_cases=[
                TestCaseCreate(
                    input=tc.input,
                    expected_output=tc.expected_output,
                    is_hidden=tc.is_hidden,
                    weight=1.0,
                )
                for tc in spec.test_cases
            ],
        ),
    )
    return GenerateChallengeResponse(
        challenge=challenge,
        contract=_learner_safe_contract(contract),
    )


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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Challenge not found",
        )
    return _challenge_to_read(challenge, learner_view=learner_view)


async def get_submission(db: AsyncSession, submission_id: int) -> SubmissionRead:
    result = await db.exec(
        select(CodeSubmission).where(CodeSubmission.id == submission_id)
    )
    submission = result.first()
    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found",
        )

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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Challenge not found",
        )
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


async def _find_idempotent_adaptive_submission(
    db: AsyncSession,
    payload: AdaptiveSubmitRequest,
) -> CodeSubmission | None:
    """Return an already graded identical official answer, if one exists."""
    result = await db.exec(
        select(CodeSubmission)
        .join(GradeResult, GradeResult.tool_session_id == CodeSubmission.id)
        .where(
            GradeResult.session_id == payload.session_id,
            GradeResult.tool_type == "coding",
            GradeResult.question_index == payload.question_index,
            CodeSubmission.challenge_id == payload.challenge_id,
            CodeSubmission.session_id == payload.session_id,
            CodeSubmission.submitted_code == payload.submitted_code,
        )
        .order_by(CodeSubmission.id)
    )
    return result.first()


async def adaptive_submit(
    db: AsyncSession, payload: AdaptiveSubmitRequest
) -> AdaptiveSubmitResponse:
    """Accept a submission, run the adaptive loop, and return the contract.

    Challenge generation is a separate ``POST /generate-challenge`` call so the
    submit request stays within frontend proxy timeouts.
    """
    existing_submission = await _find_idempotent_adaptive_submission(db, payload)
    if existing_submission is not None:
        contract = await adaptation.compute_adaptive_contract(
            db,
            payload.session_id,
            payload.assessment_id,
        )
        return AdaptiveSubmitResponse(
            submission_id=existing_submission.id or 0,
            passed=None,
            score=None,
            llm_rubric=None,
            contract=_learner_safe_contract(contract),
            next_challenge=None,
        )

    submission = await submit_code(
        db,
        SubmissionCreate(
            challenge_id=payload.challenge_id,
            session_id=payload.session_id,
            submitted_code=payload.submitted_code,
        ),
    )

    if background_grading.async_grading_enabled():
        try:
            contract, _llm_rubric, grade_id = await loop.run_adaptive_loop_fast(
                db,
                submission_id=submission.id,
                session_id=payload.session_id,
                assessment_id=payload.assessment_id,
                question_index=payload.question_index,
                difficulty=payload.difficulty,
            )
        except grading.LLMGradingUnavailable as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc

        await db.commit()
        background_grading.schedule_llm_grade_upgrade(
            grade_id=grade_id,
            session_id=payload.session_id,
            question_index=payload.question_index,
            difficulty=payload.difficulty,
        )

        return AdaptiveSubmitResponse(
            submission_id=submission.id,
            passed=None,
            score=None,
            llm_rubric=None,
            contract=_learner_safe_contract(contract),
            next_challenge=None,
        )

    try:
        contract, _llm_rubric = await loop.run_adaptive_loop(
            db,
            submission_id=submission.id,
            session_id=payload.session_id,
            assessment_id=payload.assessment_id,
            question_index=payload.question_index,
            difficulty=payload.difficulty,
        )
    except grading.LLMGradingUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    await db.commit()

    return AdaptiveSubmitResponse(
        submission_id=submission.id,
        passed=None,
        score=None,
        llm_rubric=None,
        contract=_learner_safe_contract(contract),
        next_challenge=None,
    )
