"""FastAPI dependencies for proctoring enforcement (examiner + bearer routes)."""

from __future__ import annotations

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.deps import get_db, get_session_by_token
from app.proctoring.enforcement import assert_session_ready_for_tools
from app.sessions.models import AssessmentSession


async def require_active_proctored_session(
    session: AssessmentSession = Depends(get_session_by_token),
    db: AsyncSession = Depends(get_db),
) -> AssessmentSession:
    """Bearer-authenticated session that is active and proctoring-compliant."""
    await assert_session_ready_for_tools(db, session)
    return session


__all__ = ["require_active_proctored_session"]
