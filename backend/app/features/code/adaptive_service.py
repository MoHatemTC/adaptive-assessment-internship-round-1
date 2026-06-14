"""Orchestration for the Sprint 2 adaptive coding loop."""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

from fastapi import HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.admin.service import get_platform_challenge_config
from app.challenges.generator import generate_single_adaptive_challenge
from app.challenges.schemas import UserProfile
from app.features.code.adaptation import decide_next_adaptation, initial_adaptation_decision
from app.features.code.adaptive_schemas import (
    AdaptiveSessionRead,
    AdaptiveSubmitRequest,
    AdaptiveSubmitResponse,
    LearnerCodeAnalysis,
)
from app.features.code.analysis import analyze_session
from app.features.code.audit import record_session_audit
from app.features.code.evaluation_memory import evaluate_turn_and_persist_card, load_memory_cards
from app.features.code.models import CodeAssessmentSession, CodeChallengeAttempt, SessionStatus
from app.features.code.schemas import (
    ChallengeCreate,
    SessionRead,
    TestCaseCreate,
)
from app.features.code.session_metrics import on_session_started
from app.features.code.service import (
    _load_session_context,
    create_challenge,
    get_assessment_session,
)
from app.features.code.timers import remaining_seconds, utcnow


async def _persist_generated_slot(
    db: AsyncSession,
    *,
    assessment: CodeAssessmentSession,
    generated,
    snapshot: dict,
    position: int,
    session_expires,
) -> tuple[dict, CodeChallengeAttempt]:
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
    now = utcnow()
    attempt_expires = min(
        session_expires,
        now + timedelta(seconds=generated.candidate_time_seconds),
    )
    attempt = CodeChallengeAttempt(
        assessment_session_id=assessment.id or 0,
        challenge_id=saved.id or 0,
        started_at=now,
        expires_at=attempt_expires,
    )
    db.add(attempt)
    await db.flush()

    meta = {
        "challenge_id": saved.id,
        "position": position,
        "title": generated.title,
        "language": saved.language,
        "difficulty": generated.difficulty,
        "category": generated.category,
        "requirements": generated.requirements,
        "evaluation_criteria": generated.evaluation_criteria,
        "max_score": generated.max_score,
        "estimated_duration": generated.estimated_duration,
    }
    snapshot.setdefault("challenges", []).append(meta)
    snapshot["current_difficulty"] = generated.difficulty
    assessment.config_snapshot = json.dumps(snapshot)
    db.add(assessment)
    return meta, attempt


def _session_read_to_adaptive(session: SessionRead, snapshot: dict) -> AdaptiveSessionRead:
    return AdaptiveSessionRead(
        session_id=session.session_id,
        status=session.status,
        adaptive=True,
        total_remaining_seconds=session.total_remaining_seconds,
        expires_at=session.expires_at.isoformat(),
        turns_completed=sum(1 for slot in session.challenges if slot.submitted),
        total_questions=int(snapshot.get("total_questions", len(session.challenges))),
        current_difficulty=str(snapshot.get("current_difficulty", "intermediate")),
        challenges=session.challenges,
        generation_notes=session.generation_notes,
    )


async def start_adaptive_session(
    db: AsyncSession,
    profile: UserProfile,
    *,
    platform_session_id: str | None = None,
) -> AdaptiveSessionRead:
    """Create adaptive session and generate the first challenge only."""
    config = await get_platform_challenge_config(db)
    total_questions = config.challenge.challenges_per_candidate
    now = utcnow()
    session_expires = now + timedelta(minutes=config.challenge.total_time_minutes)
    session_id = f"assess-{uuid.uuid4().hex[:12]}"
    decision = initial_adaptation_decision(profile, config)
    generated = await generate_single_adaptive_challenge(profile, config, decision)

    snapshot = {
        "adaptive": True,
        "platform_session_id": platform_session_id,
        "total_questions": total_questions,
        "platform_config": config.model_dump(),
        "generation_notes": "",
        "challenges": [],
        "current_difficulty": decision.next_difficulty,
    }
    assessment = CodeAssessmentSession(
        session_id=session_id,
        profile_json=profile.model_dump_json(),
        config_snapshot=json.dumps(snapshot),
        status=SessionStatus.ACTIVE,
        started_at=now,
        expires_at=session_expires,
    )
    db.add(assessment)
    await db.flush()

    await _persist_generated_slot(
        db,
        assessment=assessment,
        generated=generated,
        snapshot=snapshot,
        position=1,
        session_expires=session_expires,
    )
    await db.commit()
    await db.refresh(assessment)

    on_session_started()
    await record_session_audit(
        db,
        session_id=session_id,
        event_type="adaptive_session_started",
        actor="system",
        metadata={"total_questions": total_questions, "first_difficulty": decision.next_difficulty},
    )

    session = await get_assessment_session(db, session_id)
    _, _, refreshed_snapshot = await _load_session_context(db, session_id)
    return _session_read_to_adaptive(session, refreshed_snapshot)


async def submit_adaptive_turn(
    db: AsyncSession,
    session_id: str,
    payload: AdaptiveSubmitRequest,
    *,
    platform_session_id: str | None = None,
) -> AdaptiveSubmitResponse:
    """Silent submit: evaluate, analyze, optionally generate next challenge."""
    assessment, attempts, snapshot = await _load_session_context(db, session_id)
    if not snapshot.get("adaptive"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is not an adaptive session",
        )
    if assessment.status != SessionStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"Session is {assessment.status.value}",
        )

    attempt = next((a for a in attempts if a.challenge_id == payload.challenge_id), None)
    if attempt is None or attempt.submitted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Challenge not available for submission",
        )

    profile = UserProfile.model_validate_json(assessment.profile_json)
    config = await get_platform_challenge_config(db)
    total_questions = int(snapshot.get("total_questions", config.challenge.challenges_per_candidate))
    ws_platform_id = platform_session_id or snapshot.get("platform_session_id")

    (
        _tool_output,
        last_card,
        _submission,
        _grading,
        graded_attempt,
        _assessment,
        snapshot,
    ) = await evaluate_turn_and_persist_card(
        db,
        code_session_id=session_id,
        challenge_id=payload.challenge_id,
        submitted_code=payload.submitted_code,
        platform_session_id=ws_platform_id,
    )
    graded_attempt.submitted_at = utcnow()
    graded_attempt.graded_submission_id = _submission.id
    db.add(graded_attempt)

    analysis = await analyze_session(db, session_id)
    assessment.analysis_json = analysis.model_dump_json()
    db.add(assessment)

    turns_completed = analysis.turns_completed
    session_complete = turns_completed >= total_questions or remaining_seconds(assessment.expires_at) <= 0

    if not session_complete:
        cards = await load_memory_cards(db, session_id)
        decision = decide_next_adaptation(
            analysis,
            profile,
            config,
            last_card=last_card,
            current_difficulty=str(snapshot.get("current_difficulty", "intermediate")),
        )
        generated = await generate_single_adaptive_challenge(profile, config, decision)
        await _persist_generated_slot(
            db,
            assessment=assessment,
            generated=generated,
            snapshot=snapshot,
            position=len(snapshot.get("challenges", [])),
            session_expires=assessment.expires_at,
        )

    await record_session_audit(
        db,
        session_id=session_id,
        event_type="adaptive_turn_submitted",
        metadata={
            "challenge_id": payload.challenge_id,
            "turns_completed": turns_completed,
            "session_complete": session_complete,
        },
    )
    await db.commit()

    return AdaptiveSubmitResponse(
        session_id=session_id,
        status=assessment.status.value,
        turns_completed=turns_completed,
        total_questions=total_questions,
        session_complete=session_complete,
    )


async def get_adaptive_session_view(
    db: AsyncSession,
    session_id: str,
) -> AdaptiveSessionRead:
    session = await get_assessment_session(db, session_id)
    _, _, snapshot = await _load_session_context(db, session_id)
    if not snapshot.get("adaptive"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is not an adaptive session",
        )
    return _session_read_to_adaptive(session, snapshot)


async def get_adaptive_analysis(
    db: AsyncSession,
    session_id: str,
) -> LearnerCodeAnalysis:
    assessment, _, snapshot = await _load_session_context(db, session_id)
    if not snapshot.get("adaptive"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is not an adaptive session",
        )
    if assessment.analysis_json:
        return LearnerCodeAnalysis.model_validate_json(assessment.analysis_json)
    return await analyze_session(db, session_id)
