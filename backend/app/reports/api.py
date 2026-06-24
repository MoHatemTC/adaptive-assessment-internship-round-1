"""REST API for session skill radar reports."""

from fastapi import APIRouter, Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.deps import RateLimitedRoute, get_db
from app.reports.schemas import SessionRadarReport
from app.reports.service import build_session_radar_report

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
    db: AsyncSession = Depends(get_db),
) -> SessionRadarReport:
    """Return a five-dimension radar report for a completed assessment session.

    Learner-safe: dimension scores and evidence highlights only — no rubric
    breakdowns or per-question grades.
    """
    return await build_session_radar_report(db, session_id)
