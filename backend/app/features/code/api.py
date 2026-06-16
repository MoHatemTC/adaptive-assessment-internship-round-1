"""REST API routes for the code execution feature."""

from fastapi import APIRouter, Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.deps import RateLimitedRoute, get_db
from app.features.code import service
from app.features.code.schemas import (
    ChallengeCreate,
    ChallengeListItem,
    ChallengeRead,
    SubmissionCreate,
    SubmissionRead,
)

router = APIRouter(prefix="/api/v1/code", tags=["code"], route_class=RateLimitedRoute)


@router.post("/challenges", response_model=ChallengeRead, status_code=201)
async def create_challenge(
    request: Request,
    payload: ChallengeCreate,
    db: AsyncSession = Depends(get_db),
) -> ChallengeRead:
    return await service.create_challenge(db, payload)


@router.get("/challenges", response_model=list[ChallengeListItem])
async def list_challenges(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> list[ChallengeListItem]:
    return await service.list_challenges(db)


@router.get("/challenges/{challenge_id}", response_model=ChallengeRead)
async def get_challenge(
    request: Request,
    challenge_id: int,
    db: AsyncSession = Depends(get_db),
) -> ChallengeRead:
    return await service.get_challenge(db, challenge_id, learner_view=True)


@router.post("/submissions", response_model=SubmissionRead, status_code=201)
async def create_submission(
    request: Request,
    payload: SubmissionCreate,
    db: AsyncSession = Depends(get_db),
) -> SubmissionRead:
    return await service.submit_code(db, payload)


@router.get("/submissions/{submission_id}", response_model=SubmissionRead)
async def get_submission(
    request: Request,
    submission_id: int,
    db: AsyncSession = Depends(get_db),
) -> SubmissionRead:
    return await service.get_submission(db, submission_id)
