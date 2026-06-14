"""Business orchestration for code challenges and submissions."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.admin.service import get_platform_challenge_config
from app.challenges import generate_code_challenges
from app.challenges.schemas import UserProfile
from app.evaluation import evaluate_code_submission, evaluation_to_rubric_scores
from app.evaluation.schemas import CodeEvaluationContext, ScoreBreakdown
from app.features.code import tool
from app.features.code.audit import record_session_audit
from app.features.code.constants import SupportedLanguage, validate_language
from app.features.code.models import (
    CodeAssessmentSession,
    CodeChallenge,
    CodeChallengeAttempt,
    CodeRun,
    CodeSubmission,
    SessionStatus,
    SubmissionStatus,
    TestCase,
)
from app.proctoring import service as proctoring_service
from app.features.code.schemas import (
    ChallengeCreate,
    ChallengeListItem,
    ChallengeRead,
    ExecutionOutcome,
    RubricScoreRead,
    RunCreate,
    RunRead,
    SessionChallengeRead,
    SessionRead,
    SessionCompletionRead,
    SessionSubmissionsRead,
    SubmissionCreate,
    SubmissionRead,
    GeneratedChallengeRead,
    GenerateChallengesResponse,
    TestCaseCreate,
    TestCaseDTO,
    TestCaseRead,
)
from app.features.code.session_metrics import on_session_started, transition_session_status
from app.features.code.timers import assert_active, remaining_seconds, utcnow


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
        candidate_time_seconds=challenge.candidate_time_seconds,
        test_cases=test_cases,
        created_at=challenge.created_at,
        updated_at=challenge.updated_at,
    )


def _performance_ratio(results: list) -> float:
    if not results:
        return 0.0
    avg_ms = sum(r.execution_time_ms for r in results) / len(results)
    return max(0.0, round(1.0 - (avg_ms / 5000), 3))


def _submission_to_read(
    submission: CodeSubmission,
    *,
    scores: list[dict] | None = None,
    test_results: list | None = None,
    total_tests: int = 0,
    passed_tests: int = 0,
    hidden_tests_count: int = 0,
    error: str | None = None,
    evaluation: dict | None = None,
) -> SubmissionRead:
    rubric_scores = [RubricScoreRead(**s) for s in (scores or [])]
    eval_data = evaluation or {}
    breakdown_raw = eval_data.get("breakdown")
    breakdown = ScoreBreakdown(**breakdown_raw) if breakdown_raw else None
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
        evaluation_score=eval_data.get("evaluation_score"),
        evaluation_status=eval_data.get("evaluation_status"),
        breakdown=breakdown,
        strengths=eval_data.get("strengths", []),
        weaknesses=eval_data.get("weaknesses", []),
        recommendations=eval_data.get("recommendations", []),
        next_difficulty=eval_data.get("next_difficulty"),
        feedback_summary=eval_data.get("feedback_summary"),
        created_at=submission.created_at,
        updated_at=submission.updated_at,
    )


async def create_challenge(db: AsyncSession, payload: ChallengeCreate) -> ChallengeRead:
    """Persist a challenge and its test cases, then return the full read model."""
    language = (
        payload.language.value
        if isinstance(payload.language, SupportedLanguage)
        else validate_language(str(payload.language)).value
    )
    challenge = CodeChallenge(
        title=payload.title,
        description=payload.description,
        starter_code=payload.starter_code,
        language=language,
        time_limit_seconds=payload.time_limit_seconds,
        candidate_time_seconds=payload.candidate_time_seconds,
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


async def generate_challenges_from_profile(
    db: AsyncSession,
    profile: UserProfile,
    *,
    platform_config=None,
) -> GenerateChallengesResponse:
    """Generate personalized challenges via LLM and persist them to the database."""
    config = platform_config or await get_platform_challenge_config(db)
    generation = await generate_code_challenges(
        profile,
        config=config,
        prior_performance_summary=profile.prior_performance_summary,
    )

    persisted: list[GeneratedChallengeRead] = []
    for generated in generation.challenges:
        create_payload = ChallengeCreate(
            title=generated.title,
            description=generated.description,
            starter_code=generated.starter_code,
            language=generated.language,
            time_limit_seconds=generated.time_limit_seconds,
            candidate_time_seconds=generated.candidate_time_seconds,
            test_cases=[
                TestCaseCreate(
                    input=tc.input,
                    expected_output=tc.expected_output,
                    is_hidden=tc.is_hidden,
                    weight=tc.weight,
                )
                for tc in generated.test_cases
            ],
        )
        saved = await create_challenge(db, create_payload)
        persisted.append(
            GeneratedChallengeRead(
                challenge_id=saved.id,
                title=generated.title,
                difficulty=generated.difficulty,
                category=generated.category,
                description=saved.description,
                requirements=generated.requirements,
                evaluation_criteria=generated.evaluation_criteria,
                max_score=generated.max_score,
                estimated_duration=generated.estimated_duration,
                candidate_time_seconds=generated.candidate_time_seconds,
                starter_code=saved.starter_code,
                language=saved.language,
                time_limit_seconds=saved.time_limit_seconds,
                test_cases=saved.test_cases,
            )
        )

    return GenerateChallengesResponse(
        challenges=persisted,
        generation_notes=generation.generation_notes,
    )


async def list_challenges(db: AsyncSession) -> list[ChallengeListItem]:
    """Return challenge summaries ordered by id."""
    result = await db.exec(select(CodeChallenge).order_by(CodeChallenge.id))
    challenges = result.all()
    return [
        ChallengeListItem(
            id=c.id or 0,
            title=c.title,
            language=c.language,
            time_limit_seconds=c.time_limit_seconds,
            candidate_time_seconds=c.candidate_time_seconds,
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
    """Load a challenge by id; raises 404 when missing."""
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
    """Load a submission and deserialize stored grading metadata."""
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
        evaluation=metadata.get("evaluation"),
    )


async def submit_code(db: AsyncSession, payload: SubmissionCreate) -> SubmissionRead:
    """Grade submitted code in E2B and persist the submission outcome."""
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
    outcome, results, sandbox_error, _sandbox_id = await tool.execute_submission(
        payload.submitted_code,
        test_case_dtos,
        language=challenge.language,
        timeout_seconds=challenge.time_limit_seconds,
    )

    overall_score = tool.compute_weighted_score(test_case_dtos, results)
    passed_count = sum(1 for r in results if r.passed)
    visible_results = tool.filter_visible_results(test_case_dtos, results)

    eval_ctx = CodeEvaluationContext(
        challenge_id=challenge.id or payload.challenge_id,
        title=challenge.title,
        description=challenge.description,
        submitted_code=payload.submitted_code,
        language=challenge.language,
        correctness_ratio=overall_score,
        performance_ratio=_performance_ratio(results),
        passed_tests=passed_count,
        total_tests=len(test_case_dtos),
        execution_error=sandbox_error,
    )
    evaluation = await evaluate_code_submission(eval_ctx)
    scores = evaluation_to_rubric_scores(evaluation)
    passed = (
        evaluation.status == "Passed"
        and outcome == ExecutionOutcome.SUCCESS
    )
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

    if outcome == ExecutionOutcome.SUCCESS:
        submission.status = SubmissionStatus.COMPLETED
    else:
        submission.status = SubmissionStatus.FAILED

    submission.score = normalized_score
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
        evaluation=metadata.get("evaluation"),
    )


async def _load_session_context(
    db: AsyncSession,
    session_id: str,
) -> tuple[CodeAssessmentSession, list[CodeChallengeAttempt], dict]:
    result = await db.exec(
        select(CodeAssessmentSession).where(CodeAssessmentSession.session_id == session_id)
    )
    assessment = result.first()
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    attempts_result = await db.exec(
        select(CodeChallengeAttempt).where(
            CodeChallengeAttempt.assessment_session_id == assessment.id
        )
    )
    attempts = list(attempts_result.all())
    snapshot = json.loads(assessment.config_snapshot)
    return assessment, attempts, snapshot


async def _load_attempt_challenge(
    db: AsyncSession,
    attempt: CodeChallengeAttempt,
) -> CodeChallenge:
    result = await db.exec(
        select(CodeChallenge)
        .where(CodeChallenge.id == attempt.challenge_id)
        .options(selectinload(CodeChallenge.test_cases))
    )
    challenge = result.first()
    if challenge is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found")
    return challenge


async def _load_challenges_by_ids(
    db: AsyncSession,
    challenge_ids: list[int],
) -> list[CodeChallenge]:
    challenges: list[CodeChallenge] = []
    for cid in challenge_ids:
        result = await db.exec(
            select(CodeChallenge)
            .where(CodeChallenge.id == cid)
            .options(selectinload(CodeChallenge.test_cases))
        )
        loaded = result.first()
        if loaded:
            challenges.append(loaded)
    return challenges


def _session_to_read(
    assessment: CodeAssessmentSession,
    attempts: list[CodeChallengeAttempt],
    challenges: list[CodeChallenge],
    snapshot: dict,
) -> SessionRead:
    meta_by_id = {item["challenge_id"]: item for item in snapshot.get("challenges", [])}
    challenge_by_id = {c.id: c for c in challenges}
    slots: list[SessionChallengeRead] = []
    challenge_count = len(attempts)
    for position, attempt in enumerate(attempts, start=1):
        challenge = challenge_by_id.get(attempt.challenge_id)
        if challenge is None:
            continue
        meta = meta_by_id.get(attempt.challenge_id, {})
        remaining = min(
            remaining_seconds(assessment.expires_at),
            remaining_seconds(attempt.expires_at),
        )
        slots.append(
            SessionChallengeRead(
                attempt_id=attempt.id or 0,
                challenge_id=challenge.id or 0,
                position=position,
                challenge_count=challenge_count,
                title=challenge.title,
                difficulty=meta.get("difficulty", "intermediate"),
                category=meta.get("category", "general"),
                description=challenge.description,
                requirements=meta.get("requirements", []),
                evaluation_criteria=meta.get("evaluation_criteria", []),
                max_score=meta.get("max_score", 100),
                estimated_duration=meta.get("estimated_duration", ""),
                candidate_time_seconds=challenge.candidate_time_seconds,
                remaining_seconds=remaining,
                starter_code=challenge.starter_code,
                language=challenge.language,
                time_limit_seconds=challenge.time_limit_seconds,
                test_cases=_challenge_to_read(challenge, learner_view=True).test_cases,
                submitted=attempt.submitted_at is not None,
                run_count=attempt.run_count,
            )
        )
    return SessionRead(
        session_id=assessment.session_id,
        status=assessment.status.value,
        total_remaining_seconds=remaining_seconds(assessment.expires_at),
        expires_at=assessment.expires_at,
        challenges=slots,
        generation_notes=snapshot.get("generation_notes", ""),
        adaptive=bool(snapshot.get("adaptive")),
        turns_completed=sum(1 for a in attempts if a.submitted_at is not None),
        total_questions=int(snapshot.get("total_questions", len(attempts))),
        current_difficulty=str(snapshot.get("current_difficulty", "intermediate")),
    )


async def start_assessment_session(
    db: AsyncSession,
    profile: UserProfile,
) -> SessionRead:
    """Create a timed session, generate challenges, and attach per-challenge timers."""
    config = await get_platform_challenge_config(db)
    generation_response = await generate_challenges_from_profile(
        db,
        profile,
        platform_config=config,
    )
    now = utcnow()
    session_expires = now + timedelta(minutes=config.challenge.total_time_minutes)
    session_id = f"assess-{uuid.uuid4().hex[:12]}"
    manifest = {
        "platform_config": config.model_dump(),
        "generation_notes": generation_response.generation_notes,
        "challenges": [
            {
                "challenge_id": c.challenge_id,
                "position": index,
                "title": c.title,
                "language": c.language,
                "difficulty": c.difficulty,
                "category": c.category,
                "requirements": c.requirements,
                "evaluation_criteria": c.evaluation_criteria,
                "max_score": c.max_score,
                "estimated_duration": c.estimated_duration,
            }
            for index, c in enumerate(generation_response.challenges, start=1)
        ],
    }
    assessment = CodeAssessmentSession(
        session_id=session_id,
        profile_json=profile.model_dump_json(),
        config_snapshot=json.dumps(manifest),
        status=SessionStatus.ACTIVE,
        started_at=now,
        expires_at=session_expires,
    )
    db.add(assessment)
    await db.flush()

    attempts: list[CodeChallengeAttempt] = []
    for generated in generation_response.challenges:
        attempt_expires = min(
            session_expires,
            now + timedelta(seconds=generated.candidate_time_seconds),
        )
        attempt = CodeChallengeAttempt(
            assessment_session_id=assessment.id or 0,
            challenge_id=generated.challenge_id,
            started_at=now,
            expires_at=attempt_expires,
        )
        db.add(attempt)
        attempts.append(attempt)

    await db.commit()
    await db.refresh(assessment)
    for attempt in attempts:
        await db.refresh(attempt)

    on_session_started()
    await record_session_audit(
        db,
        session_id=session_id,
        event_type="session_started",
        actor="system",
        metadata={"challenge_count": len(generation_response.challenges)},
    )

    challenge_ids = [c.challenge_id for c in generation_response.challenges]
    challenges = await _load_challenges_by_ids(db, challenge_ids)
    return _session_to_read(assessment, attempts, challenges, manifest)


async def list_session_submissions(
    db: AsyncSession,
    session_id: str,
) -> SessionSubmissionsRead:
    """Return graded submissions for all challenges in a session."""
    _, attempts, _ = await _load_session_context(db, session_id)
    submissions: list[SubmissionRead] = []
    for attempt in attempts:
        if attempt.graded_submission_id is None:
            continue
        submissions.append(await get_submission(db, attempt.graded_submission_id))
    return SessionSubmissionsRead(session_id=session_id, submissions=submissions)


async def get_assessment_session(db: AsyncSession, session_id: str) -> SessionRead:
    assessment, attempts, snapshot = await _load_session_context(db, session_id)
    challenge_ids = [a.challenge_id for a in attempts]
    challenges = await _load_challenges_by_ids(db, challenge_ids)
    if remaining_seconds(assessment.expires_at) <= 0 and assessment.status == SessionStatus.ACTIVE:
        transition_session_status(assessment, SessionStatus.EXPIRED)
        db.add(assessment)
        await db.commit()
    return _session_to_read(assessment, attempts, challenges, snapshot)


async def _resolve_attempt(
    db: AsyncSession,
    session_id: str,
    challenge_id: int,
) -> tuple[CodeAssessmentSession, CodeChallengeAttempt, CodeChallenge, dict]:
    assessment, attempts, snapshot = await _load_session_context(db, session_id)
    if assessment.status == SessionStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assessment session is completed and locked",
        )
    if assessment.status != SessionStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"Session is {assessment.status.value}",
        )
    assert_active(assessment.expires_at, label="Assessment session")
    attempt = next((a for a in attempts if a.challenge_id == challenge_id), None)
    if attempt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not in session")
    if attempt.submitted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Challenge already submitted for grading",
        )
    assert_active(attempt.expires_at, label="Challenge attempt")
    challenge = await _load_attempt_challenge(db, attempt)
    return assessment, attempt, challenge, snapshot


async def run_code(db: AsyncSession, payload: RunCreate) -> RunRead:
    """Execute visible tests only; unlimited runs until timers expire."""
    assessment, attempt, challenge, snapshot = await _resolve_attempt(
        db,
        payload.session_id,
        payload.challenge_id,
    )
    remaining = min(
        remaining_seconds(assessment.expires_at),
        remaining_seconds(attempt.expires_at),
    )
    test_case_dtos = [_test_case_to_dto(tc) for tc in challenge.test_cases]
    platform = snapshot.get("platform_config", {})
    e2b_template = platform.get("challenge", {}).get("e2b_template")
    outcome, results, sandbox_error, new_sandbox_id = await tool.execute_submission(
        payload.submitted_code,
        test_case_dtos,
        language=challenge.language,
        timeout_seconds=challenge.time_limit_seconds,
        sandbox_id=attempt.e2b_sandbox_id,
        keep_sandbox=True,
        include_hidden=False,
        template=e2b_template,
    )
    if new_sandbox_id:
        attempt.e2b_sandbox_id = new_sandbox_id
    attempt.run_count += 1
    db.add(attempt)
    visible_cases = [tc for tc in test_case_dtos if not tc.is_hidden]
    visible = tool.filter_visible_results(visible_cases, results)
    passed_count = sum(1 for r in results if r.passed)
    db.add(
        CodeRun(
            attempt_id=attempt.id or 0,
            outcome=outcome.value,
            passed_tests=passed_count,
            total_tests=len(results),
            error=sandbox_error,
        )
    )
    await db.commit()
    return RunRead(
        outcome=outcome,
        test_results=visible,
        passed_tests=passed_count,
        total_tests=len(results),
        error=sandbox_error,
        remaining_seconds=remaining,
        run_count=attempt.run_count,
    )


async def submit_session_challenge(
    db: AsyncSession,
    payload: RunCreate,
) -> SubmissionRead:
    """Final graded submission — full tests, LLM evaluation, one per challenge."""
    from app.features.code.grading import grade_submission_in_sandbox, persist_graded_submission

    assessment, attempt, challenge, snapshot = await _resolve_attempt(
        db,
        payload.session_id,
        payload.challenge_id,
    )
    platform = snapshot.get("platform_config", {})
    e2b_template = platform.get("challenge", {}).get("e2b_template")
    test_case_dtos = [_test_case_to_dto(tc) for tc in challenge.test_cases]

    grading = await grade_submission_in_sandbox(
        challenge=challenge,
        submitted_code=payload.submitted_code,
        session_id=payload.session_id,
        test_case_dtos=test_case_dtos,
        e2b_template=e2b_template,
        kill_existing_sandbox_id=attempt.e2b_sandbox_id,
    )
    attempt.e2b_sandbox_id = None

    submission = await persist_graded_submission(
        db,
        challenge_id=payload.challenge_id,
        session_id=payload.session_id,
        submitted_code=payload.submitted_code,
        grading=grading,
    )

    attempt.submitted_at = utcnow()
    attempt.graded_submission_id = submission.id
    db.add(attempt)

    await record_session_audit(
        db,
        session_id=payload.session_id,
        event_type="challenge_submitted",
        metadata={
            "challenge_id": payload.challenge_id,
            "submission_id": submission.id,
            "passed": grading.passed,
            "evaluation_score": grading.evaluation.score,
        },
    )

    await db.commit()
    await db.refresh(submission)

    return _submission_to_read(
        submission,
        scores=grading.scores,
        test_results=grading.visible_results,
        total_tests=grading.metadata["total_tests"],
        passed_tests=grading.metadata["passed_tests"],
        hidden_tests_count=grading.metadata["hidden_tests_count"],
        error=grading.metadata.get("error"),
        evaluation=grading.metadata.get("evaluation"),
    )


async def complete_assessment_session(
    db: AsyncSession,
    session_id: str,
    *,
    confirm_unsubmitted: bool = False,
) -> SessionCompletionRead:
    """Formally complete a session: kill sandboxes, lock editing, audit log."""
    assessment, attempts, _ = await _load_session_context(db, session_id)
    if assessment.status == SessionStatus.COMPLETED:
        return await _completion_read_for_session(db, assessment, attempts)
    if assessment.status != SessionStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"Session is {assessment.status.value} and cannot be completed",
        )

    unsubmitted = [a.challenge_id for a in attempts if a.submitted_at is None]
    if unsubmitted and not confirm_unsubmitted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Some challenges have not been submitted for grading",
                "unsubmitted_challenge_ids": unsubmitted,
            },
        )

    for attempt in attempts:
        if attempt.e2b_sandbox_id:
            await tool.kill_sandbox(attempt.e2b_sandbox_id)
            attempt.e2b_sandbox_id = None
            db.add(attempt)

    now = utcnow()
    assessment.completed_at = now
    transition_session_status(assessment, SessionStatus.COMPLETED)
    db.add(assessment)

    integrity_score: int | None = None
    integrity_risk: str | None = None
    try:
        report = await proctoring_service.get_integrity_report(db, session_id)
        integrity_score = report.integrity_score
        integrity_risk = report.risk_level
    except Exception:  # noqa: BLE001 — proctoring is best-effort on completion
        pass

    submitted_count = sum(1 for a in attempts if a.submitted_at is not None)
    await record_session_audit(
        db,
        session_id=session_id,
        event_type="session_completed",
        actor="candidate",
        metadata={
            "challenges_submitted": submitted_count,
            "challenges_total": len(attempts),
            "unsubmitted_challenge_ids": unsubmitted,
            "integrity_score": integrity_score,
            "integrity_risk_level": integrity_risk,
            "confirm_unsubmitted": confirm_unsubmitted,
        },
    )
    await db.commit()
    await db.refresh(assessment)
    return await _completion_read_for_session(db, assessment, attempts)


async def _completion_read_for_session(
    db: AsyncSession,
    assessment: CodeAssessmentSession,
    attempts: list[CodeChallengeAttempt],
) -> SessionCompletionRead:
    unsubmitted = [a.challenge_id for a in attempts if a.submitted_at is None]
    submitted_count = sum(1 for a in attempts if a.submitted_at is not None)
    integrity_score: int | None = None
    integrity_risk: str | None = None
    try:
        report = await proctoring_service.get_integrity_report(db, assessment.session_id)
        integrity_score = report.integrity_score
        integrity_risk = report.risk_level
    except Exception:  # noqa: BLE001
        pass

    message = "Assessment completed successfully."
    if unsubmitted:
        message = (
            f"Assessment completed with {len(unsubmitted)} unsubmitted challenge(s). "
            "Unsubmitted work was not graded."
        )

    return SessionCompletionRead(
        session_id=assessment.session_id,
        status=assessment.status.value,
        completed_at=assessment.completed_at or utcnow(),
        challenges_submitted=submitted_count,
        challenges_total=len(attempts),
        unsubmitted_challenge_ids=unsubmitted,
        integrity_score=integrity_score,
        integrity_risk_level=integrity_risk,
        message=message,
    )
