"""REST API routes for the code execution feature."""

from fastapi import APIRouter, Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.deps import RateLimitedRoute, get_db
from app.features.code import adaptive_service
from app.features.code.adaptive_schemas import (
    AdaptiveSessionRead,
    AdaptiveSubmitRequest,
    AdaptiveSubmitResponse,
    LearnerCodeAnalysis,
)
from app.features.code import service
from pydantic import BaseModel, Field

from app.features.code.schemas import (
    ChallengeCreate,
    ChallengeListItem,
    ChallengeRead,
    GenerateChallengesResponse,
    RunCreate,
    RunRead,
    SessionCompletionRead,
    SessionRead,
    SessionSubmissionsRead,
    SubmissionCreate,
    SubmissionRead,
    UserProfile,
)


class SessionCompleteRequest(BaseModel):
    confirm_unsubmitted: bool = Field(
        default=False,
        description="Set true when finishing with unsubmitted challenges",
    )

router = APIRouter(route_class=RateLimitedRoute)


@router.post("/sessions", response_model=SessionRead, status_code=201)
async def start_session(
    request: Request,
    profile: UserProfile,
    db: AsyncSession = Depends(get_db),
) -> SessionRead:
    """Start a timed assessment: profile → generate N challenges → per-challenge timers."""
    return await service.start_assessment_session(db, profile)


@router.get("/sessions/{session_id}", response_model=SessionRead)
async def get_session(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> SessionRead:
    """Fetch session status, timers, and challenge slots."""
    return await service.get_assessment_session(db, session_id)


@router.post("/sessions/{session_id}/complete", response_model=SessionCompletionRead)
async def complete_session(
    request: Request,
    session_id: str,
    payload: SessionCompleteRequest,
    db: AsyncSession = Depends(get_db),
) -> SessionCompletionRead:
    """Formally finish the assessment: lock editing and record an audit event."""
    return await service.complete_assessment_session(
        db,
        session_id,
        confirm_unsubmitted=payload.confirm_unsubmitted,
    )


@router.get("/sessions/{session_id}/submissions", response_model=SessionSubmissionsRead)
async def list_session_submissions(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> SessionSubmissionsRead:
    """List graded submissions for every challenge in the session."""
    return await service.list_session_submissions(db, session_id)


@router.post("/runs", response_model=RunRead, status_code=201)
async def run_code(
    request: Request,
    payload: RunCreate,
    db: AsyncSession = Depends(get_db),
) -> RunRead:
    """Run visible tests in E2B (unlimited until timer expires)."""
    return await service.run_code(db, payload)


@router.post("/challenges/generate", response_model=GenerateChallengesResponse, status_code=201)
async def generate_challenges(
    request: Request,
    profile: UserProfile,
    db: AsyncSession = Depends(get_db),
) -> GenerateChallengesResponse:
    """Generate personalized challenges from a user profile (LLM-only authoring)."""
    return await service.generate_challenges_from_profile(db, profile)


@router.post("/challenges", response_model=ChallengeRead, status_code=201)
async def create_challenge(
    request: Request,
    payload: ChallengeCreate,
    db: AsyncSession = Depends(get_db),
) -> ChallengeRead:
    """Create a code challenge with its test cases."""
    return await service.create_challenge(db, payload)


@router.get("/challenges", response_model=list[ChallengeListItem])
async def list_challenges(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> list[ChallengeListItem]:
    """List all code challenges (summary fields only)."""
    return await service.list_challenges(db)


@router.get("/challenges/{challenge_id}", response_model=ChallengeRead)
async def get_challenge(
    request: Request,
    challenge_id: int,
    db: AsyncSession = Depends(get_db),
) -> ChallengeRead:
    """Fetch a challenge for the learner view (hidden expected outputs omitted)."""
    return await service.get_challenge(db, challenge_id, learner_view=True)


@router.post("/submissions", response_model=SubmissionRead, status_code=201)
async def create_submission(
    request: Request,
    payload: SubmissionCreate,
    db: AsyncSession = Depends(get_db),
) -> SubmissionRead:
    """Submit learner code for final grading (session or legacy direct submit)."""
    if payload.session_id.startswith("assess-"):
        return await service.submit_session_challenge(
            db,
            RunCreate(
                session_id=payload.session_id,
                challenge_id=payload.challenge_id,
                submitted_code=payload.submitted_code,
            ),
        )
    return await service.submit_code(db, payload)


@router.get("/submissions/{submission_id}", response_model=SubmissionRead)
async def get_submission(
    request: Request,
    submission_id: int,
    db: AsyncSession = Depends(get_db),
) -> SubmissionRead:
    """Retrieve a persisted submission with grading metadata."""
    return await service.get_submission(db, submission_id)


@router.post("/adaptive/sessions", response_model=AdaptiveSessionRead, status_code=201)
async def start_adaptive_session(
    request: Request,
    profile: UserProfile,
    db: AsyncSession = Depends(get_db),
) -> AdaptiveSessionRead:
    """Start adaptive session: profile → first adapted challenge only."""
    return await adaptive_service.start_adaptive_session(db, profile)


@router.get("/adaptive/sessions/{session_id}", response_model=AdaptiveSessionRead)
async def get_adaptive_session(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> AdaptiveSessionRead:
    """Fetch adaptive session with loop metadata and challenge slots."""
    return await adaptive_service.get_adaptive_session_view(db, session_id)


@router.post(
    "/adaptive/sessions/{session_id}/submit",
    response_model=AdaptiveSubmitResponse,
    status_code=201,
)
async def submit_adaptive_turn(
    request: Request,
    session_id: str,
    payload: AdaptiveSubmitRequest,
    db: AsyncSession = Depends(get_db),
) -> AdaptiveSubmitResponse:
    """Submit one turn silently; evaluate, analyze, and adapt next challenge."""
    return await adaptive_service.submit_adaptive_turn(db, session_id, payload)


@router.get(
    "/adaptive/sessions/{session_id}/analysis",
    response_model=LearnerCodeAnalysis,
)
async def get_adaptive_analysis(
    request: Request,
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> LearnerCodeAnalysis:
    """Mentor/debug view of dimension estimates (not learner scores)."""
    return await adaptive_service.get_adaptive_analysis(db, session_id)
