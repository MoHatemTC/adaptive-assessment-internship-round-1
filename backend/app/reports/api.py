"""REST API for session skill radar reports."""

from fastapi import APIRouter, Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.deps import RateLimitedRoute, get_db
from app.reports.deps import require_completed_session_for_radar
from app.reports.schemas import SessionRadarReport
from app.reports.service import build_session_radar_report
from app.sessions.models import AssessmentSession

router = APIRouter(
    prefix="/api/v1/reports",
    tags=["reports"],
    route_class=RateLimitedRoute,
)


@router.get(
    "/sessions/{session_id}/radar",
    response_model=SessionRadarReport,
)
async def get_session_radar_report(
    request: Request,
    session_id: str,
    session: AssessmentSession = Depends(require_completed_session_for_radar),
    db: AsyncSession = Depends(get_db),
) -> SessionRadarReport:
    """Return a five-dimension radar report for a completed assessment session.

    Requires admin JWT or the owning learner session bearer token. Mid-session
    partial scores are never returned (silent grading).
    """
    _ = session
    return await build_session_radar_report(db, session_id)
