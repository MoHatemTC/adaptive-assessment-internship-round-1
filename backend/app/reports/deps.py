"""Authorization dependencies for report endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.deps import get_db, oauth2_scheme
from app.core.security import hash_token, verify_access_token
from app.sessions.models import AssessmentSession


async def authorize_radar_report_access(
    session_id: str,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> AssessmentSession:
    """Allow admins or the owning learner session token to read a radar report."""
    session = await db.get(AssessmentSession, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment session not found.",
        )

    if verify_access_token(token) is not None:
        return session

    hashed_token = hash_token(token)
    result = await db.exec(
        select(AssessmentSession).where(
            AssessmentSession.token_hash == hashed_token,
            AssessmentSession.expires_at > datetime.now(timezone.utc),
        )
    )
    owned = result.first()
    if owned is None or owned.id != session_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this report.",
        )
    return session


async def require_completed_session_for_radar(
    session: AssessmentSession = Depends(authorize_radar_report_access),
) -> AssessmentSession:
    """Block mid-assessment score leakage — reports are post-completion only."""
    if session.status == "pending_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Report is awaiting admin review before it can be released.",
        )
    if session.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Report is only available after the assessment is completed.",
        )
    return session
